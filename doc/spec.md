# nostr投稿前チェック機能付き投稿専門クライアント prenos

## これはなに？
nostrに投稿するクライアントですが、予めどの観点でチェックを行えば良いのか伝えておくとそれに従ってチェックをしてから投稿を行います。状況次第ではLLMからの質問もあります。

## 技術スタック
- python 3.14以降
- uv
- openai API, Gemini API, local LLM(ollama, LM studio)が利用できる
- UIはStreamlit

## 各種データの保存

- nostr投稿に使用するnsec（秘密キー）は.envに記載する
- .envファイルはGit管理対象外とする
- nostrの投稿内容、LLMとのやり取り、チェック結果などはsqliteに保存する
- チェック観点はユーザーがagent.mdに記載し、システムがそれを読み理解する


