import asyncio
from nostr_sdk import Keys, Client, NostrSigner, RelayUrl, EventBuilder

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
