import os
import sys
import difflib
import json
from dotenv import load_dotenv

# Ensure Streamlit is imported
import streamlit as st

# Import our custom modules
import db
import llm
import nostr_client

# Load environment variables
load_dotenv()

# Default relays if none are set in the DB settings
DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.nostr.band",
    "wss://yabu.me"
]

def init_defaults():
    """Initializes default settings in the database if not present."""
    db.init_db()
    if db.get_setting("relays") is None:
        db.save_setting("relays", DEFAULT_RELAYS)
    if db.get_setting("llm_provider") is None:
        db.save_setting("llm_provider", "openai")
    if db.get_setting("openai_model") is None:
        db.save_setting("openai_model", "gpt-4o-mini")
    if db.get_setting("gemini_model") is None:
        db.save_setting("gemini_model", "gemini-1.5-flash")
    if db.get_setting("ollama_endpoint") is None:
        db.save_setting("ollama_endpoint", "http://localhost:11434/v1")
    if db.get_setting("ollama_model") is None:
        db.save_setting("ollama_model", "llama3")
    if db.get_setting("lm_studio_endpoint") is None:
        db.save_setting("lm_studio_endpoint", "http://localhost:1234/v1")
    if db.get_setting("lm_studio_model") is None:
        db.save_setting("lm_studio_model", "meta-llama-3-8b-instruct")

def get_char_diff_html(old_text: str, new_text: str) -> str:
    """Generates a beautiful HTML inline difference representation."""
    matcher = difflib.SequenceMatcher(None, old_text, new_text)
    html = []
    for opcode, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if opcode == 'equal':
            html.append(old_text[a_start:a_end])
        elif opcode == 'insert':
            inserted = new_text[b_start:b_end]
            html.append(f'<span style="background-color: rgba(46, 125, 50, 0.35); border-bottom: 2px solid #2e7d32; padding: 0px 2px; border-radius: 2px; color: #a1e8a1; font-weight: bold;">{inserted}</span>')
        elif opcode == 'delete':
            deleted = old_text[a_start:a_end]
            html.append(f'<span style="background-color: rgba(198, 40, 40, 0.35); text-decoration: line-through; padding: 0px 2px; border-radius: 2px; color: #ff9e9e;">{deleted}</span>')
        elif opcode == 'replace':
            deleted = old_text[a_start:a_end]
            inserted = new_text[b_start:b_end]
            html.append(f'<span style="background-color: rgba(198, 40, 40, 0.35); text-decoration: line-through; padding: 0px 2px; border-radius: 2px; color: #ff9e9e;">{deleted}</span>')
            html.append(f'<span style="background-color: rgba(46, 125, 50, 0.35); border-bottom: 2px solid #2e7d32; padding: 0px 2px; border-radius: 2px; color: #a1e8a1; font-weight: bold;">{inserted}</span>')
            
    return "".join(html).replace("\n", "<br>")

def update_env_file(key: str, value: str):
    """Safely updates or adds a key-value pair in .env file."""
    env_lines = []
    found = False
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            env_lines = f.readlines()
            
    new_lines = []
    for line in env_lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
            
    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}={value}\n")
        
    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    # Reload env vars
    load_dotenv(override=True)

def run_streamlit_app():
    # Page configurations
    st.set_page_config(page_title="prenos - Nostr Check Client", page_icon="📡", layout="wide")
    
    init_defaults()
    
    # Premium CSS styling injection
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .title-banner {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #db2777 100%);
        padding: 2.5rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 10px 25px rgba(79, 70, 229, 0.15);
        position: relative;
        overflow: hidden;
    }
    .title-banner::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 60%);
        animation: spin 30s linear infinite;
        pointer-events: none;
    }
    @keyframes spin { 100% { transform:rotate(360deg); } }
    
    .status-badge {
        font-weight: 600;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        display: inline-block;
    }
    
    .badge-approved { background-color: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-warning { background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-question { background-color: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .badge-posted { background-color: rgba(139, 92, 246, 0.2); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); }
    .badge-failed { background-color: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .badge-draft { background-color: rgba(107, 114, 128, 0.2); color: #9ca3af; border: 1px solid rgba(107, 114, 128, 0.3); }
    
    .card-panel {
        background-color: rgba(30, 41, 59, 0.6);
        border-radius: 12px;
        padding: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.08);
        margin-bottom: 1.25rem;
        transition: all 0.25s ease;
    }
    .card-panel:hover {
        border-color: rgba(255, 255, 255, 0.15);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
    }
    
    .diff-box {
        font-family: 'JetBrains Mono', monospace;
        background-color: #0f172a;
        padding: 1.25rem;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        margin: 1rem 0;
        line-height: 1.6;
    }
    
    .info-footer {
        text-align: center;
        font-size: 0.8rem;
        color: #64748b;
        margin-top: 3rem;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
        padding-top: 1.5rem;
    }

    .image-upload-section {
        background: linear-gradient(135deg, rgba(79, 70, 229, 0.08) 0%, rgba(124, 58, 237, 0.12) 100%);
        border: 1px solid rgba(124, 58, 237, 0.3);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin: 1rem 0 0.5rem 0;
    }
    .image-upload-section h4 {
        margin: 0 0 0.75rem 0;
        color: #a78bfa;
        font-weight: 600;
        font-size: 1rem;
    }
    .img-meta-row {
        display: flex;
        gap: 1.5rem;
        font-size: 0.82rem;
        color: #94a3b8;
        margin-top: 0.4rem;
    }
    .img-meta-row span { white-space: nowrap; }
    .upload-success-box {
        background-color: rgba(16, 185, 129, 0.1);
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-top: 0.75rem;
        word-break: break-all;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        color: #34d399;
    }
    </style>
    """, unsafe_allow_html=True)

    # App Header Banner
    st.markdown("""
    <div class="title-banner">
        <h1 style="margin: 0; font-weight: 700; font-size: 2.5rem; color: white;">📡 prenos (プレノス)</h1>
        <p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-size: 1.1rem;">AIチェック機能付き・対話型 Nostr 投稿専門クライアント</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Check for secret key in environment
    nsec_env = os.environ.get("NOSTR_NSEC", "") or os.environ.get("NSEC", "")
    nsec_valid = nostr_client.validate_nsec(nsec_env) if nsec_env else False
    
    if not nsec_env:
        st.warning("⚠️ Nostrの秘密キー (nsec) が .env に設定されていません。「設定」タブで設定してください。")
    elif not nsec_valid:
        st.error("❌ .env に設定されている nsec (秘密キー) のフォーマットが正しくありません。")
    else:
        npub = nostr_client.get_public_key_from_nsec(nsec_env)
        st.success(f"🔐 Nostr ログイン中: `{npub[:14]}...{npub[-10:]}`")

    # Session State Initialization
    if "draft_text" not in st.session_state:
        st.session_state.draft_text = ""
    if "check_status" not in st.session_state:
        st.session_state.check_status = "idle"  # idle, checking, approved, warning, question, posted, failed, error
    if "post_id" not in st.session_state:
        st.session_state.post_id = None
    if "llm_result" not in st.session_state:
        st.session_state.llm_result = None
    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []
    if "user_answer" not in st.session_state:
        st.session_state.user_answer = ""
    if "relay_publish_results" not in st.session_state:
        st.session_state.relay_publish_results = None
    if "uploaded_image_url" not in st.session_state:
        st.session_state.uploaded_image_url = None
    if "draft_text_update" not in st.session_state:
        st.session_state.draft_text_update = None

    # Tabs
    tab_post, tab_agent, tab_history, tab_settings = st.tabs([
        "📝 新規投稿", 
        "⚙️ チェック基準編集", 
        "📜 履歴ブラウザ", 
        "🛠️ システム設定"
    ])
    
    # ----------------- TAB 1: NEW POST -----------------
    with tab_post:
        st.subheader("下書きを作成")

        # Check if we have a pending update to the draft text (prevents StreamlitAPIException)
        if st.session_state.draft_text_update is not None:
            st.session_state.draft_text = st.session_state.draft_text_update
            st.session_state.draft_text_input = st.session_state.draft_text_update
            st.session_state.draft_text_update = None
        
        # Check if they have an active LLM suggestion to apply
        def apply_suggestion(sug_text):
            st.session_state.draft_text_update = sug_text  # 安全に次の描画で反映する
            st.session_state.check_status = "idle"
            st.session_state.llm_result = None
            st.session_state.conversation_history = []
            
        # Draft textarea
        # To make it interactive and support updating the value dynamically, we bind it to a value but handle changes
        draft_input = st.text_area(
            "投稿メッセージを入力してください:",
            value=st.session_state.draft_text,
            height=150,
            placeholder="ここにNostrに書き込む下書きを入力してください...",
            key="draft_text_input"
        )
        
        # Keep internal draft_text updated
        st.session_state.draft_text = draft_input

        # --------------- IMAGE UPLOAD SECTION ---------------
        st.markdown('<div class="image-upload-section"><h4>🖼️ 画像を添付する (image.nostr.build)</h4></div>', unsafe_allow_html=True)

        if not nsec_valid:
            st.warning("⚠️ 画像アップロードには Nostr 秘密キーの設定が必要です。「🛠️ システム設定」タブで設定してください。", icon="🔒")
        else:
            uploaded_file = st.file_uploader(
                "画像ファイルを選択またはドロップ（PNG / JPG / WEBP / GIF、最大 20MB）:",
                type=["png", "jpg", "jpeg", "webp", "gif"],
                key="image_uploader",
                label_visibility="collapsed"
            )

            if uploaded_file is not None:
                file_bytes = uploaded_file.getvalue()
                file_size_kb = len(file_bytes) / 1024
                file_size_str = f"{file_size_kb:.1f} KB" if file_size_kb < 1024 else f"{file_size_kb / 1024:.2f} MB"

                col_prev, col_meta = st.columns([1, 2])
                with col_prev:
                    st.image(file_bytes, caption="プレビュー", use_container_width=True)
                with col_meta:
                    st.markdown(f"""
                    <div class="img-meta-row">
                        <span>📄 <strong>{uploaded_file.name}</strong></span>
                    </div>
                    <div class="img-meta-row">
                        <span>📦 サイズ: {file_size_str}</span>
                        <span>🎨 形式: {uploaded_file.type}</span>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("📤 画像サーバーにアップロード", type="primary", key="upload_image_btn"):
                        with st.spinner("image.nostr.build にアップロード中..."):
                            upload_result = nostr_client.upload_image_to_nostr_build(
                                nsec=nsec_env,
                                file_bytes=file_bytes,
                                filename=uploaded_file.name,
                                mime_type=uploaded_file.type
                            )

                        if upload_result["success"]:
                            img_url = upload_result["url"]
                            st.session_state.uploaded_image_url = img_url
                            # Append image URL to draft text
                            current_draft = st.session_state.draft_text.rstrip()
                            new_draft = (current_draft + "\n" + img_url) if current_draft else img_url
                            # st.session_state.draft_text_input はウィジェットインスタンス化後は書き換えられないため、
                            # draft_text_update に保存して次の rerun の描画前に適用させる。
                            st.session_state.draft_text_update = new_draft
                            st.toast("✅ 画像のアップロードに成功しました！", icon="🎉")
                            st.rerun()
                        else:
                            st.error(f"❌ アップロード失敗: {upload_result['error_message']}")

            # Show last uploaded URL (persists across reruns)
            if st.session_state.uploaded_image_url:
                st.markdown(f"""
                <div class="upload-success-box">
                    ✅ アップロード済み: {st.session_state.uploaded_image_url}
                </div>
                """, unsafe_allow_html=True)
                if st.button("🗑️ アップロード済み URL をクリア", key="clear_img_url_btn"):
                    st.session_state.uploaded_image_url = None
                    st.rerun()

        st.write("")
        # ----- end image upload section -----

        col_actions = st.columns([1, 1, 4])
        
        # Button: Trigger AI check
        with col_actions[0]:
            btn_check = st.button("🤖 AIチェックを実行", type="primary", use_container_width=True)
            
        # Button: Reset Draft
        with col_actions[1]:
            if st.button("🧹 下書きをクリア", use_container_width=True):
                st.session_state.draft_text_update = ""  # 安全に次の描画前でクリアする
                st.session_state.check_status = "idle"
                st.session_state.llm_result = None
                st.session_state.conversation_history = []
                st.session_state.relay_publish_results = None
                st.session_state.uploaded_image_url = None
                st.rerun()

        if btn_check:
            if not st.session_state.draft_text.strip():
                st.error("下書きが空です。投稿する文章を入力してください。")
            else:
                st.session_state.check_status = "checking"
                st.session_state.relay_publish_results = None
                st.rerun()

        # Handle Checking State
        if st.session_state.check_status == "checking":
            with st.spinner("AIがチェック観点に沿って下書きを検査しています..."):
                # 1. Create a DB record for this check
                prov = db.get_setting("llm_provider", "openai")
                model_name = db.get_setting(f"{prov}_model") if prov in ("openai", "gemini") else db.get_setting(f"{prov}_model")
                post_id = db.create_post(
                    original_content=st.session_state.draft_text, 
                    status="checking",
                    llm_provider=prov,
                    llm_model=model_name
                )
                st.session_state.post_id = post_id
                st.session_state.conversation_history = []
                
                # 2. Call LLM
                result = llm.check_draft_with_llm(st.session_state.draft_text, [])
                
                # 3. Update DB & State based on result
                if result.get("status") == "error":
                    st.session_state.check_status = "error"
                    st.session_state.llm_result = result
                    db.update_post(post_id, status="failed", llm_metadata={"error": result["error_message"]})
                else:
                    st.session_state.check_status = result["status"]
                    st.session_state.llm_result = result
                    
                    # Log first turn of conversation
                    initial_history = [
                        {"role": "user", "content": f"チェック対象の下書き:\n「{st.session_state.draft_text}」"},
                        {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)}
                    ]
                    st.session_state.conversation_history = initial_history
                    
                    # Update database with results
                    db.update_post(
                        post_id, 
                        status=result["status"],
                        conversation_history=initial_history,
                        llm_metadata=result
                    )
            st.rerun()

        # Show Evaluation Results
        if st.session_state.llm_result:
            result = st.session_state.llm_result
            status = st.session_state.check_status
            
            st.write("---")
            st.subheader("🔍 AIチェック結果")
            
            if status == "approved":
                st.markdown(f'<div class="status-badge badge-approved">✅ 合格 (Approved)</div>', unsafe_allow_html=True)
                st.markdown(f"""
                <div class="card-panel approved-card" style="margin-top: 0.5rem;">
                    <h4 style="margin: 0 0 0.5rem 0; color: #34d399;">投稿に最適です！</h4>
                    <p style="margin: 0; color: #e2e8f0;">{result.get('explanation', '')}</p>
                </div>
                """, unsafe_allow_html=True)
                
            elif status == "warning":
                st.markdown(f'<div class="status-badge badge-warning">⚠️ 要確認 (Warning)</div>', unsafe_allow_html=True)
                st.markdown(f"""
                <div class="card-panel warning-card" style="margin-top: 0.5rem;">
                    <h4 style="margin: 0 0 0.5rem 0; color: #fbbf24;">修正箇所・警告があります</h4>
                    <p style="margin: 0; color: #e2e8f0;">{result.get('explanation', '')}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Suggestions & Diff Highlight
                sugs = result.get("suggestions", [])
                if sugs:
                    st.markdown("##### 📝 提案された修正案と差分:")
                    for idx, sug in enumerate(sugs):
                        diff_html = get_char_diff_html(st.session_state.draft_text, sug)
                        st.markdown(f'<div class="diff-box">{diff_html}</div>', unsafe_allow_html=True)
                        
                        if st.button(f"🤖 提案 {idx+1} を下書きに適用する", key=f"apply_sug_{idx}"):
                            apply_suggestion(sug)
                            st.toast("修正案を下書きに適用しました。")
                            st.rerun()
                            
            elif status == "question":
                st.markdown(f'<div class="status-badge badge-question">💬 LLMからの確認事項 (Question)</div>', unsafe_allow_html=True)
                st.markdown(f"""
                <div class="card-panel question-card" style="margin-top: 0.5rem;">
                    <h4 style="margin: 0 0 0.5rem 0; color: #60a5fa;">チェック完了のため、質問にお答えください</h4>
                    <p style="margin: 0; color: #e2e8f0; font-size: 1.1rem; font-weight: 600;">{result.get('question', '')}</p>
                    <p style="margin: 0.5rem 0 0 0; color: #94a3b8; font-size: 0.9rem;">解説: {result.get('explanation', '')}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Show Conversation History in Q&A loop
                if len(st.session_state.conversation_history) > 2:
                    with st.expander("💬 これまでのやりとりを表示"):
                        for turn in st.session_state.conversation_history:
                            role_label = "あなた" if turn["role"] == "user" else "AI"
                            role_color = "#38bdf8" if turn["role"] == "user" else "#a78bfa"
                            
                            content_disp = turn["content"]
                            # If assistant block, print it cleanly rather than raw JSON
                            if turn["role"] == "assistant":
                                try:
                                    js = json.loads(turn["content"])
                                    if js.get("question"):
                                        content_disp = f"質問: {js.get('question')}\n(解説: {js.get('explanation')})"
                                    elif js.get("status") == "approved":
                                        content_disp = f"チェック結果: 合格\n(解説: {js.get('explanation')})"
                                    elif js.get("status") == "warning":
                                        content_disp = f"チェック結果: 警告あり\n(解説: {js.get('explanation')})"
                                except Exception:
                                    pass
                            
                            st.markdown(f'<strong style="color: {role_color};">{role_label}</strong>: {content_disp}', unsafe_allow_html=True)
                
                # Input for user answer
                user_ans = st.text_input("質問への回答を入力してください:", key="user_answer_input")
                
                if st.button("✉️ 回答を送信して再検証"):
                    if not user_ans.strip():
                        st.error("回答が空です。")
                    else:
                        with st.spinner("回答を踏まえて再チェック中..."):
                            # Update session state history
                            hist = st.session_state.conversation_history
                            hist.append({"role": "user", "content": user_ans})
                            
                            # Re-run check with updated history
                            new_res = llm.check_draft_with_llm(st.session_state.draft_text, hist)
                            
                            if new_res.get("status") == "error":
                                st.session_state.check_status = "error"
                                st.session_state.llm_result = new_res
                                db.update_post(st.session_state.post_id, status="failed", llm_metadata={"error": new_res["error_message"]})
                            else:
                                hist.append({"role": "assistant", "content": json.dumps(new_res, ensure_ascii=False)})
                                st.session_state.check_status = new_res["status"]
                                st.session_state.llm_result = new_res
                                st.session_state.conversation_history = hist
                                
                                # Update SQLite DB
                                db.update_post(
                                    st.session_state.post_id, 
                                    status=new_res["status"],
                                    conversation_history=hist,
                                    llm_metadata=new_res
                                )
                        st.toast("再検証が完了しました。")
                        st.rerun()
                        
            elif status == "error":
                st.markdown(f'<div class="status-badge badge-failed">❌ エラー (Error)</div>', unsafe_allow_html=True)
                st.markdown(f"""
                <div class="card-panel error-card" style="margin-top: 0.5rem;">
                    <h4 style="margin: 0 0 0.5rem 0; color: #f87171;">エラーが発生しました</h4>
                    <p style="margin: 0; color: #e2e8f0;">{result.get('error_message', '')}</p>
                </div>
                """, unsafe_allow_html=True)
                
            # Publishing Section (Approved or Warnings can be published)
            if status in ("approved", "warning") and nsec_valid:
                st.markdown("---")
                st.subheader("🚀 Nostrへ投稿")
                
                final_post_text = st.text_area("送信する最終メッセージ (必要に応じて微調整):", value=st.session_state.draft_text)
                
                # Active relays display
                relays_list = db.get_setting("relays", DEFAULT_RELAYS)
                st.markdown(f"送信先リレー: {', '.join([f'`{r}`' for r in relays_list])}")
                
                if st.button("📤 Nostrに投稿する", type="primary", key="publish_btn"):
                    with st.spinner("リレーに送信中..."):
                        res = nostr_client.publish_note(nsec_env, final_post_text, relays_list)
                        st.session_state.relay_publish_results = res
                        
                        if res.get("success"):
                            st.session_state.check_status = "posted"
                            # Update post in SQLite
                            db.update_post(
                                st.session_state.post_id,
                                status="posted",
                                final_content=final_post_text,
                                event_id=res["event_id"],
                                relay_results=res
                            )
                        else:
                            st.session_state.check_status = "failed"
                            db.update_post(
                                st.session_state.post_id,
                                status="failed",
                                final_content=final_post_text,
                                llm_metadata={"publish_error": res.get("error_message")}
                            )
                    st.rerun()

        # Display Final Publish Status
        if st.session_state.check_status == "posted" and st.session_state.relay_publish_results:
            res = st.session_state.relay_publish_results
            st.success("🎉 Nostrへの投稿が完了しました！")
            
            st.markdown(f"**Event ID:** `{res['event_id']}`")
            # Links to live nostr web client
            st.markdown(f"🔗 [njump で投稿を見る (njump.me)](https://njump.me/{res['event_id']}) | [nostr.band で見る](https://nostr.band/get/{res['event_id']})")
            
            # Relay list
            st.markdown("#### 📡 リレー送信状況:")
            for success_relay in res.get("published_relays", []):
                st.markdown(f"- ✅ `{success_relay}`: 送信成功")
            for fail_relay, err in res.get("failed_relays", {}).items():
                st.markdown(f"- ❌ `{fail_relay}`: 失敗 ({err})")
                
        elif st.session_state.check_status == "failed" and st.session_state.relay_publish_results:
            res = st.session_state.relay_publish_results
            st.error(f"❌ 投稿の送信に失敗しました: {res.get('error_message', 'リレー通信エラー')}")

    # ----------------- TAB 2: AGENT.MD EDITOR -----------------
    with tab_agent:
        st.subheader("チェック観点 (agent.md) の編集")
        st.info("💡 ここで指定した観点は、AIが下書きを検証する際の厳格な命令として読み込まれます。")
        
        # Load agent.md
        criteria_content = llm.load_agent_criteria()
        
        agent_edit = st.text_area(
            "agent.md の内容:",
            value=criteria_content,
            height=300,
            key="agent_criteria_editor"
        )
        
        if st.button("💾 設定を保存する", type="primary"):
            try:
                with open("agent.md", "w", encoding="utf-8") as f:
                    f.write(agent_edit)
                st.success("💾 agent.md の保存に成功しました！次回チェックから即時反映されます。")
                st.rerun()
            except Exception as e:
                st.error(f"保存エラー: {str(e)}")

    # ----------------- TAB 3: HISTORY -----------------
    with tab_history:
        st.subheader("過去のチェック・投稿ログ")
        
        posts = db.get_all_posts(limit=100)
        
        if not posts:
            st.write("過去の投稿・チェック履歴はまだありません。")
        else:
            for p in posts:
                post_id = p["id"]
                created_at = p["created_at"]
                orig_text = p["original_content"]
                status = p["status"]
                
                # Map status to color badge
                badge_html = f'<div class="status-badge badge-{status}">{status.upper()}</div>'
                
                title_disp = f"#{post_id} - {created_at} | {orig_text[:40]}..."
                
                with st.expander(title_disp):
                    col_info = st.columns([1, 4])
                    with col_info[0]:
                        st.markdown(f"**状態:** {badge_html}", unsafe_allow_html=True)
                        st.markdown(f"**日時:** `{created_at}`")
                        st.markdown(f"**LLM:** `{p['llm_provider']} ({p['llm_model']})`")
                        if p.get("event_id"):
                            st.markdown(f"🔗 [njump](https://njump.me/{p['event_id']})")
                    with col_info[1]:
                        st.markdown("**下書き内容:**")
                        st.code(orig_text)
                        
                        if p.get("final_content") and p.get("final_content") != orig_text:
                            st.markdown("**実際に送信した内容:**")
                            st.code(p["final_content"])
                            
                        # Show DB stored metadata and suggestions if warning
                        meta = p.get("llm_metadata", {})
                        if meta:
                            if meta.get("explanation"):
                                st.info(f"💡 **AIの判定根拠:** {meta.get('explanation')}")
                            if meta.get("suggestions"):
                                st.markdown("**修正提案:**")
                                for sug in meta["suggestions"]:
                                    st.markdown(f"- `{sug}`")
                                    
                        # Show conversation history
                        history_turns = p.get("conversation_history", [])
                        if history_turns:
                            st.markdown("**🔍 対話チェック記録:**")
                            for turn in history_turns:
                                role_color = "#38bdf8" if turn["role"] == "user" else "#a78bfa"
                                role_label = "あなた" if turn["role"] == "user" else "AI"
                                content_disp = turn["content"]
                                
                                if turn["role"] == "assistant":
                                    try:
                                        js = json.loads(turn["content"])
                                        content_disp = f"{js.get('status').upper()} - {js.get('explanation')}"
                                        if js.get("question"):
                                            content_disp += f"\n質問: {js.get('question')}"
                                    except Exception:
                                        pass
                                st.markdown(f'<strong style="color: {role_color};">{role_label}:</strong> {content_disp}', unsafe_allow_html=True)
                                
                        # Show publishing relay results
                        relay_res = p.get("relay_results", {})
                        if relay_res:
                            st.markdown("**📡 リレー送信結果:**")
                            st.write(f"Event ID: `{relay_res.get('event_id', '')}`")
                            for success_relay in relay_res.get("published_relays", []):
                                st.markdown(f"- ✅ `{success_relay}`")
                            for fail_relay, err in relay_res.get("failed_relays", {}).items():
                                st.markdown(f"- ❌ `{fail_relay}`: {err}")

    # ----------------- TAB 4: SYSTEM SETTINGS -----------------
    with tab_settings:
        st.subheader("🤖 AIプロバイダー設定")
        
        current_provider = db.get_setting("llm_provider", "openai")
        
        provider_options = ["openai", "gemini", "ollama", "lm_studio"]
        prov_idx = provider_options.index(current_provider) if current_provider in provider_options else 0
        
        llm_provider = st.selectbox(
            "利用するLLMプロバイダーを選択してください:",
            options=provider_options,
            index=prov_idx,
            format_func=lambda x: {
                "openai": "OpenAI API (GPT-4oなど)",
                "gemini": "Gemini API (Gemini 1.5/2.0など)",
                "ollama": "Ollama (ローカル・オフライン)",
                "lm_studio": "LM Studio (ローカル・オフライン)"
            }[x]
        )
        
        if llm_provider != current_provider:
            db.save_setting("llm_provider", llm_provider)
            st.success(f"プロバイダーを {llm_provider} に変更しました。")
            st.rerun()
            
        # Context-dependent provider configurations
        if llm_provider == "openai":
            st.markdown("#### OpenAI 設定")
            openai_key = st.text_input("OpenAI API Key (未入力の場合は環境変数から読み込み):", value=db.get_setting("openai_api_key", ""), type="password")
            openai_model = st.text_input("利用モデル名:", value=db.get_setting("openai_model", "gpt-4o-mini"))
            
            if st.button("💾 OpenAI設定を保存", key="save_openai_btn"):
                db.save_setting("openai_api_key", openai_key)
                db.save_setting("openai_model", openai_model)
                st.success("OpenAI設定を保存しました！")
                st.rerun()
                
        elif llm_provider == "gemini":
            st.markdown("#### Gemini 設定")
            gemini_key = st.text_input("Gemini API Key (未入力の場合は環境変数から読み込み):", value=db.get_setting("gemini_api_key", ""), type="password")
            gemini_model = st.text_input("利用モデル名:", value=db.get_setting("gemini_model", "gemini-1.5-flash"))
            
            if st.button("💾 Gemini設定を保存", key="save_gemini_btn"):
                db.save_setting("gemini_api_key", gemini_key)
                db.save_setting("gemini_model", gemini_model)
                st.success("Gemini設定を保存しました！")
                st.rerun()
                
        elif llm_provider == "ollama":
            st.markdown("#### Ollama (ローカルLLM) 設定")
            ollama_endpoint = st.text_input("APIエンドポイント (Base URL):", value=db.get_setting("ollama_endpoint", "http://localhost:11434/v1"))
            ollama_model = st.text_input("利用モデル名 (例: llama3, qwen2.5, phi3):", value=db.get_setting("ollama_model", "llama3"))
            
            st.info("💡 ローカルPCでOllamaを起動し、指定モデルが pull されている必要があります。")
            
            if st.button("💾 Ollama設定を保存", key="save_ollama_btn"):
                db.save_setting("ollama_endpoint", ollama_endpoint)
                db.save_setting("ollama_model", ollama_model)
                st.success("Ollama設定を保存しました！")
                st.rerun()
                
        elif llm_provider == "lm_studio":
            st.markdown("#### LM Studio (ローカルLLM) 設定")
            lms_endpoint = st.text_input("APIエンドポイント (Base URL):", value=db.get_setting("lm_studio_endpoint", "http://localhost:1234/v1"))
            lms_model = st.text_input("利用モデル名 (LM Studio側でロードしているモデル名):", value=db.get_setting("lm_studio_model", "meta-llama-3-8b-instruct"))
            
            st.info("💡 LM Studioのローカルサーバー (Local Server) を開始している必要があります。")
            
            if st.button("💾 LM Studio設定を保存", key="save_lms_btn"):
                db.save_setting("lm_studio_endpoint", lms_endpoint)
                db.save_setting("lm_studio_model", lms_model)
                st.success("LM Studio設定を保存しました！")
                st.rerun()

        st.markdown("---")
        st.subheader("📡 Nostr リレー設定")
        
        current_relays = db.get_setting("relays", DEFAULT_RELAYS)
        
        # Display current relays list
        st.write("現在のアクティブなリレーリスト:")
        for idx, r_url in enumerate(current_relays):
            col_rel, col_del = st.columns([5, 1])
            col_rel.code(r_url)
            if col_del.button("🗑️ 削除", key=f"del_relay_{idx}"):
                new_rel = current_relays.copy()
                new_rel.pop(idx)
                db.save_setting("relays", new_rel)
                st.toast(f"リレー {r_url} をリストから削除しました。")
                st.rerun()
                
        # Add new relay
        new_relay_input = st.text_input("新しく追加するリレーのURL:", placeholder="wss://...")
        if st.button("➕ リレーを追加"):
            if not new_relay_input.strip() or not new_relay_input.startswith("wss://"):
                st.error("有効な wss:// 形式のリレーURLを入力してください。")
            elif new_relay_input in current_relays:
                st.warning("このリレーは既に登録されています。")
            else:
                new_rel = current_relays.copy()
                new_rel.append(new_relay_input.strip())
                db.save_setting("relays", new_rel)
                st.toast(f"リレー {new_relay_input} を追加しました。")
                st.rerun()

        st.markdown("---")
        st.subheader("🔐 Nostr 鍵設定 (.env)")
        
        # Display existing .env setup status
        if nsec_env:
            st.info(f"現在、環境変数・.envから秘密キーが読み込まれています。\n対応する npub: `{npub}`")
        else:
            st.warning("現在、秘密キーが設定されていません。投稿を行うには nsec 秘密キーの設定が必要です。")
            
        nsec_input = st.text_input("Nostr 秘密キー (nsec... 形式または 64文字のHEXキー):", type="password", placeholder="nsec1...")
        
        col_keys = st.columns([1, 1, 2])
        with col_keys[0]:
            if st.button("💾 秘密キーを保存", type="primary"):
                if not nsec_input.strip():
                    st.error("鍵を入力してください。")
                elif not nostr_client.validate_nsec(nsec_input.strip()):
                    st.error("入力された鍵の形式が正しくありません。(nsec... または 64桁のHEXである必要があります)")
                else:
                    # Update .env
                    update_env_file("NOSTR_NSEC", nsec_input.strip())
                    st.success("🔐 秘密キーを .env に安全に保存しました！")
                    st.rerun()
        with col_keys[1]:
            if st.button("⚡ テスト用新キーペア生成"):
                nsec_gen, npub_gen = nostr_client.generate_new_keypair()
                st.code(f"Generated nsec (秘密キー):\n{nsec_gen}\n\nGenerated npub (公開キー):\n{npub_gen}")
                st.info("💡 テスト用に利用できます。秘密キー (nsec) は安全に保管してください。")

    # Beautiful footer
    st.markdown("""
    <div class="info-footer">
        prenos client v0.1.0 • Built with Streamlit, Python & nostr-sdk • Running on local environment
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    from streamlit.runtime import exists
    if not exists():
        # Outside Streamlit, start it!
        import subprocess
        print("Starting prenos via Streamlit...")
        try:
            # First try using uv
            subprocess.run(["uv", "run", "streamlit", "run", __file__])
        except Exception:
            # Fallback to sys executable
            subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])
        sys.exit(0)
    else:
        # Inside Streamlit
        run_streamlit_app()
