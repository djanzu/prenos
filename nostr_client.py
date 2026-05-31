import asyncio
import base64
import requests
from nostr_sdk import Keys, Client, NostrSigner, RelayUrl, EventBuilder, HttpData, HttpMethod

def validate_nsec(nsec: str) -> bool:
    """Validates if the provided string is a valid secret key (hex or bech32 nsec)."""
    try:
        Keys.parse(nsec)
        return True
    except Exception:
        return False

def get_public_key_from_nsec(nsec: str) -> str:
    """Converts a secret key into a bech32 npub address. Returns empty string if invalid."""
    try:
        keys = Keys.parse(nsec)
        return keys.public_key().to_bech32()
    except Exception:
        return ""

def generate_new_keypair() -> tuple[str, str]:
    """Generates a new random keypair. Returns (nsec, npub)."""
    keys = Keys.generate()
    nsec = keys.secret_key().to_bech32()
    npub = keys.public_key().to_bech32()
    return nsec, npub

async def publish_note_async(nsec: str, content: str, relays: list[str]) -> dict:
    """Async publishing function."""
    try:
        keys = Keys.parse(nsec)
        signer = NostrSigner.keys(keys)
        client = Client(signer)
        
        # Add all relays
        added_any = False
        for r_url in relays:
            r_url = r_url.strip()
            if not r_url:
                continue
            try:
                url_obj = RelayUrl.parse(r_url)
                await client.add_relay(url_obj)
                added_any = True
            except Exception as e:
                print(f"Failed to parse or add relay {r_url}: {e}")
                
        if not added_any:
            return {
                "success": False,
                "error_message": "No valid relays were configured."
            }
            
        # Connect to relays
        await client.connect()
        
        # Build event
        builder = EventBuilder.text_note(content)
        
        # Send event
        output = await client.send_event_builder(builder)
        
        # Disconnect client
        await client.disconnect()
        
        # Parse output
        success_list = [str(r) for r in output.success]
        failed_dict = {str(r): err for r, err in output.failed.items()}
        
        return {
            "success": True,
            "event_id": output.id.to_hex(),
            "published_relays": success_list,
            "failed_relays": failed_dict
        }
    except Exception as e:
        return {
            "success": False,
            "error_message": str(e)
        }

def publish_note(nsec: str, content: str, relays: list[str]) -> dict:
    """
    Synchronously publishes a note to the listed relays using nsec secret key.
    Returns a dict with publishing results.
    """
    return asyncio.run(publish_note_async(nsec, content, relays))


def upload_image_to_nostr_build(nsec: str, file_bytes: bytes, filename: str, mime_type: str) -> dict:
    """
    Uploads an image to image.nostr.build using NIP-98 (HTTP Auth for Nostr) authentication.

    Args:
        nsec:       The user's Nostr secret key (bech32 nsec or 64-char hex).
        file_bytes: Raw bytes of the image file to upload.
        filename:   Original filename (e.g., "photo.jpg").
        mime_type:  MIME type of the file (e.g., "image/jpeg", "image/png").

    Returns:
        A dict with keys:
          - "success" (bool)
          - "url" (str) — the public URL on image.nostr.build (on success)
          - "error_message" (str) — human-readable error description (on failure)
    """
    # Validate nsec and parse keys
    try:
        keys = Keys.parse(nsec)
    except Exception as e:
        return {"success": False, "error_message": f"秘密キーが無効です: {str(e)}"}

    upload_url = "https://nostr.build/api/v2/upload/files"

    try:
        # Build NIP-98 Kind 27235 ephemeral event signed with the user's key
        http_data = HttpData(url=upload_url, method=HttpMethod.POST, payload=None)
        event = EventBuilder.http_auth(http_data).sign_with_keys(keys)
        b64_event = base64.b64encode(event.as_json().encode("utf-8")).decode("utf-8")

        headers = {
            "Authorization": f"Nostr {b64_event}"
        }
        files = {
            "fileToUpload": (filename, file_bytes, mime_type)
        }

        response = requests.post(upload_url, headers=headers, files=files, timeout=30)

        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("status") == "success" and res_json.get("data"):
                file_info = res_json["data"][0]
                return {
                    "success": True,
                    "url": file_info["url"],
                    "mime": file_info.get("mime", mime_type),
                    "size": file_info.get("size", 0),
                    "sha256": file_info.get("sha256", ""),
                    "dimensions": file_info.get("dimensionsString", ""),
                    "thumbnail": file_info.get("thumbnail", ""),
                }
            else:
                return {
                    "success": False,
                    "error_message": res_json.get("message", "アップロードに失敗しました（詳細不明）")
                }
        elif response.status_code == 401:
            return {
                "success": False,
                "error_message": "認証エラー (401): NIP-98 トークンが無効です。秘密キーを確認してください。"
            }
        elif response.status_code == 413:
            return {
                "success": False,
                "error_message": "ファイルサイズが大きすぎます (413)。nostr.build の無料プランのファイルサイズ制限を超えています。"
            }
        else:
            return {
                "success": False,
                "error_message": f"アップロード失敗 (HTTP {response.status_code}): {response.text[:200]}"
            }

    except requests.exceptions.Timeout:
        return {"success": False, "error_message": "アップロードがタイムアウトしました (30秒)。ネットワーク接続を確認してください。"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error_message": "image.nostr.build への接続に失敗しました。ネットワーク接続を確認してください。"}
    except Exception as e:
        return {"success": False, "error_message": f"予期しないエラー: {str(e)}"}
