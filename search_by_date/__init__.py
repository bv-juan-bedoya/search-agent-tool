import os
import azure.functions as func
import logging
import json
import html
import requests
import re
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import ListSortOrder

# 🔧 Configuration from environment
AI_PROJECT_ENDPOINT = os.getenv("AI_PROJECT_ENDPOINT")
AGENT_ID = os.getenv("AGENT_ID")
MAIN_AGENT_DEPLOYMENT = os.getenv("AZURE_OAI_DEPLOYMENT")
AZURE_OAI_ENDPOINT = os.getenv("AZURE_OAI_ENDPOINT")
AZURE_OAI_KEY = os.getenv("AZURE_OAI_KEY")
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")

# 🔌 Initialize AI Project client
try:
    project = AIProjectClient(
        credential=DefaultAzureCredential(),
        endpoint=AI_PROJECT_ENDPOINT
    )
    logging.info("✅ AIProjectClient initialized")
except Exception as e:
    logging.warning(f"⚠️ Failed to initialize AIProjectClient: {e}")
    project = None

# 📅 Date parsing via Foundry Agent
def call_date_parser_agent(user_query: str) -> dict:
    if not project:
        raise ValueError("AI Project client unavailable")
    try:
        agent = project.agents.get_agent(AGENT_ID)
        thread = project.agents.threads.create()
        project.agents.messages.create(thread_id=thread.id, role="user", content=user_query)
        run = project.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        if run.status == "failed":
            raise ValueError(f"Agent failed: {run.last_error}")
        messages = project.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
        for msg in messages:
            if msg.role == "assistant" and msg.text_messages:
                response_text = msg.text_messages[-1].text.value.strip()
                if response_text.startswith('{') and response_text.endswith('}'):
                    return json.loads(response_text)
                match = re.search(r'\{.*?\}', response_text)
                if match:
                    return json.loads(match.group())
        raise ValueError("No valid JSON output from agent")
    except Exception as e:
        logging.error(f"❌ Date parser agent error: {e}")
        raise

# 📅 Fallback parser (basic heuristic)
def fallback_date_parser(user_query: str) -> dict:
    today = datetime.utcnow().date()
    q = user_query.lower()
    if "última semana" in q or "semana pasada" in q:
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        return {"start": start.isoformat(), "end": end.isoformat()}
    elif "ayer" in q:
        return {"date": (today - timedelta(days=1)).isoformat()}
    elif "hoy" in q:
        return {"date": today.isoformat()}
    else:
        last_month = today.replace(day=1) - timedelta(days=1)
        start_last = last_month.replace(day=1)
        return {"start": start_last.isoformat(), "end": last_month.isoformat()}

# 🔍 Build Cognitive Search filter expression
def build_filter_expression(date_data: dict) -> str:
    if "date" in date_data:
        d = parse_date(date_data["date"]).date().isoformat()
        return f"metadata_spo_item_release_date eq {d}T00:00:00Z"
    elif "start" in date_data and "end" in date_data:
        start = parse_date(date_data["start"]).date().isoformat()
        end = parse_date(date_data["end"]).date().isoformat()
        return f"(metadata_spo_item_release_date ge {start}T00:00:00Z and metadata_spo_item_release_date le {end}T23:59:59Z)"
    return ""

# 🎯 Query AOYD (RAG agent) with filter
def call_rag_agent_with_filter(user_query: str, filter_expression: str) -> dict:
    url = f"{AZURE_OAI_ENDPOINT}/openai/deployments/{MAIN_AGENT_DEPLOYMENT}/extensions/chat/completions?api-version=2023-10-01-preview"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OAI_KEY
    }
    body = {
        "messages": [ {"role": "user", "content": user_query} ],
        "dataSources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "endpoint": AZURE_SEARCH_ENDPOINT,
                    "indexName": AZURE_SEARCH_INDEX,
                    "key": AZURE_SEARCH_API_KEY,
                    "filter": filter_expression,
                    "semanticConfiguration": "docs-index-semantic-confg",
                    "topNDocuments": 10
                }
            }
        ],
        "temperature": 0.2,
        "top_p": 1,
        "max_tokens": 800
    }
    try:
        logging.info("📡 Calling AOYD with filter: " + filter_expression)
        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"🚫 AOYD call failed: {e}")
        raise

# 🚀 Azure Function entrypoint
def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        raw_query = req.params.get("q")
        if not raw_query:
            return func.HttpResponse("Missing 'q' parameter", status_code=400)

        user_query = html.unescape(raw_query)
        logging.info(f"🗣️ Received query: {user_query}")

        # Step 1: Date parsing
        try:
            parsed_date_info = call_date_parser_agent(user_query)
        except Exception as e:
            logging.warning(f"⚠️ Agent fallback triggered: {e}")
            parsed_date_info = fallback_date_parser(user_query)

        # Step 2: Build filter
        filter_expression = build_filter_expression(parsed_date_info)
        if not filter_expression:
            return func.HttpResponse("No valid date found in query.", status_code=400)

        # Step 3: Call AOYD
        gpt_response = call_rag_agent_with_filter(user_query, filter_expression)

        # Final response
        output = {
            "parsed_dates": parsed_date_info,
            "filter": filter_expression,
            "gpt_answer": gpt_response["choices"][0]["message"]["content"]
        }
        return func.HttpResponse(
            json.dumps(output, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.exception("🔥 Unhandled error")
        return func.HttpResponse(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500
        )