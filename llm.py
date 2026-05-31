import os
import re
import json
from openai import OpenAI
import google.generativeai as genai
from dotenv import load_dotenv

import db

# Load environment variables (from .env)
load_dotenv()

AGENT_FILE_PATH = "agent.md"

def load_agent_criteria() -> str:
    """Loads checking criteria from agent.md. If it doesn't exist, returns a default."""
    if os.path.exists(AGENT_FILE_PATH):
        try:
            with open(AGENT_FILE_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            return f"Error loading agent.md: {str(e)}"
    return "特に指定なし（投稿内容の文脈や誤字脱字を一般的な観点からチェックしてください）"

def extract_json(text: str) -> dict:
    """Robustly extracts and parses JSON from the LLM text response."""
    text_clean = text.strip()
    
    # 1. Direct JSON parse
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass
        
    # 2. Markdown code block check (e.g. ```json ... ``` or ``` ... ```)
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, text_clean, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
            
    # 3. Direct search for boundaries of curly braces
    start = text_clean.find('{')
    end = text_clean.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text_clean[start:end+1].strip())
        except json.JSONDecodeError:
            pass
            
    raise ValueError("Could not parse JSON from LLM response. Original text:\n" + text)

def build_system_prompt(criteria: str) -> str:
    """Generates the system instruction prompt."""
    return f"""あなたはNostr投稿用の下書きを検査するAIチェックアシスタントです。
以下の「ユーザー指定のチェック観点」に基づいて、入力された投稿内容（下書き）を徹底的にチェックしてください。

【ユーザー指定のチェック観点（agent.mdの内容）】
{criteria}

【役割と動作仕様】
1. 投稿内容がチェック観点に完全に適合し、かつ文脈や誤字脱字、ミス変換に問題がない場合は、投稿可能（approved）と判定してください。
2. 誤字脱字やミス変換（特に「言って」と「行って」、「企業」と「起業」の混同など）の可能性があり、修正案が提示できる場合は、警告・要確認（warning）と判定してください。suggestionsリストに修正案（修正後の投稿内容）を記述してください。
3. 投稿内容が極めて曖昧である、またはチェック観点と照らし合わせるために不足している情報があり、ユーザーに直接意図を確認したい場合は、質問（question）と判定してください。questionフィールドにユーザーに投げかける具体的な質問文を日本語で記述してください。

【出力要件】
出力は必ず以下の構造を持つJSON形式のみとしてください。解説や余計なマークアップ（コードブロックを除く）は含めないでください。

{{
  "status": "approved" | "warning" | "question",
  "explanation": "どのような観点からチェックを行い、この判定に至ったかの分かりやすい説明（日本語）",
  "suggestions": [
    "修正案の全文（statusが 'warning' の場合。複数ある場合は複数提示可）"
  ],
  "question": "ユーザーへの質問内容（statusが 'question' の場合のみ）"
}}

※出力は必ずJSONオブジェクトで終わるようにし、説明のプレフィックスなどは一切出力しないでください。"""

def check_draft_with_llm(
    draft_content: str, 
    conversation_history: list = None
) -> dict:
    """
    Checks the draft content using the configured LLM.
    Supports OpenAI, Gemini, Ollama, and LM Studio.
    `conversation_history` is a list of dicts: [{"role": "user"|"assistant", "content": "..."}]
    """
    if conversation_history is None:
        conversation_history = []
        
    # Get settings from db
    provider = db.get_setting("llm_provider", "openai")
    
    criteria = load_agent_criteria()
    sys_prompt = build_system_prompt(criteria)
    
    # Prepare API inputs
    api_key_env = ""
    model_name = ""
    base_url = None
    
    if provider == "openai":
        api_key_env = os.environ.get("OPENAI_API_KEY", "")
        db_key = db.get_setting("openai_api_key", "")
        api_key = db_key if db_key else api_key_env
        model_name = db.get_setting("openai_model", "gpt-5-mini")
        if not api_key:
            return {"status": "error", "error_message": "OpenAI API Key is not configured. Please set it in Settings."}
            
    elif provider == "gemini":
        api_key_env = os.environ.get("GEMINI_API_KEY", "")
        db_key = db.get_setting("gemini_api_key", "")
        api_key = db_key if db_key else api_key_env
        model_name = db.get_setting("gemini_model", "gemini-3.5-flash")
        if not api_key:
            return {"status": "error", "error_message": "Gemini API Key is not configured. Please set it in Settings."}
            
    elif provider == "ollama":
        api_key = "ollama" # placeholder
        base_url = db.get_setting("ollama_endpoint", "http://localhost:11434/v1")
        model_name = db.get_setting("ollama_model", "gemma4:latest")
        
    elif provider == "lm_studio":
        api_key = "lm_studio" # placeholder
        base_url = db.get_setting("lm_studio_endpoint", "http://localhost:1234/v1")
        model_name = db.get_setting("lm_studio_model", "openai/gpt-oss-20b")
        
    else:
        return {"status": "error", "error_message": f"Unknown LLM provider: {provider}"}

    # Construct the full list of messages for the API call
    messages = []
    
    # We will build standard OpenAI message structure
    # For Ollama, LM Studio, OpenAI:
    messages.append({"role": "system", "content": sys_prompt})
    
    # Append past history if any
    for turn in conversation_history:
        messages.append({"role": turn["role"], "content": turn["content"]})
        
    # Append the current check target if history is empty, or the user's latest response
    if not conversation_history:
        messages.append({"role": "user", "content": f"チェック対象の下書き:\n「{draft_content}」"})
    else:
        # If history already has messages, user has answered a question. We don't need to append the draft again,
        # but just ensure the latest user turn is present. We assume the caller managed conversation_history properly.
        pass

    try:
        if provider in ("openai", "ollama", "lm_studio"):
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"} if provider == "openai" else None
            )
            reply_text = response.choices[0].message.content
            
        elif provider == "gemini":
            # Native Gemini integration
            genai.configure(api_key=api_key)
            
            # Format history for Gemini API
            # Gemini GenerativeModel takes system_instruction as parameter.
            # The history contains alternating 'user' and 'model' (which corresponds to 'assistant' in OpenAI terms)
            gemini_history = []
            
            # We process the user-provided turns
            # We skip the first message if it's the system instruction, which we supply separately
            for msg in messages:
                if msg["role"] == "system":
                    continue
                role = "user" if msg["role"] == "user" else "model"
                gemini_history.append({"role": role, "parts": [msg["content"]]})
                
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=sys_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Start chat session or generate single message
            if len(gemini_history) > 1:
                # Setup chat history except the last message
                chat = model.start_chat(history=gemini_history[:-1])
                response = chat.send_message(gemini_history[-1]["parts"][0])
            else:
                response = model.generate_content(gemini_history[0]["parts"][0])
                
            reply_text = response.text
            
        # Parse the JSON response
        result = extract_json(reply_text)
        
        # Validate keys in result to ensure it has correct fields
        result.setdefault("status", "approved")
        result.setdefault("explanation", "チェックが完了しました。")
        result.setdefault("suggestions", [])
        result.setdefault("question", "")
        
        return result
        
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"LLM Call failed ({provider} - {model_name}): {str(e)}"
        }
