import os
import azure.functions as func
import logging
import json
import requests
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder

# Azure AI Agent configuration
AI_PROJECT_ENDPOINT = os.getenv("AI_PROJECT_ENDPOINT")
AGENT_ID = os.getenv("AGENT_ID")

# Initialize Azure AI Project Client
try:
    project = AIProjectClient(
        credential=DefaultAzureCredential(),
        endpoint=AI_PROJECT_ENDPOINT
    )
    logging.info("Azure AI Project Client initialized successfully")
except Exception as e:
    logging.warning(f"Failed to initialize Azure AI Project Client: {e}")
    project = None

# Azure Cognitive Search Configuration
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

def call_date_parser_agent(user_query: str) -> dict:
    """Uses the Azure AI Agent to parse dates."""
    if not project:
        raise ValueError("Azure AI Project client not available - check authentication")
        
    try:
        # Get the agent
        agent = project.agents.get_agent(AGENT_ID)
        
        # Create a new thread for this conversation
        thread = project.agents.threads.create()
        logging.info(f"Created thread, ID: {thread.id}")
        
        # Create a message with the user query
        message = project.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_query
        )
        
        # Run the agent
        run = project.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id
        )
        
        if run.status == "failed":
            logging.error(f"Agent run failed: {run.last_error}")
            raise ValueError(f"Agent run failed: {run.last_error}")
        
        # Get the messages from the thread
        messages = project.agents.messages.list(
            thread_id=thread.id, 
            order=ListSortOrder.ASCENDING
        )
        
        # Find the agent's response (last message from assistant)
        agent_response = None
        for message in messages:
            if message.role == "assistant" and message.text_messages:
                agent_response = message.text_messages[-1].text.value
        
        if not agent_response:
            logging.error("No response from agent")
            raise ValueError("No response from agent")
        
        logging.info(f"Agent response: {agent_response}")
        
        # Try to extract JSON from the response
        agent_response = agent_response.strip()
        
        # Try to extract JSON from the response if it contains extra text
        if agent_response.startswith('{') and agent_response.endswith('}'):
            return json.loads(agent_response)
        else:
            # Try to find JSON within the response
            import re
            json_match = re.search(r'\{[^{}]*\}', agent_response)
            if json_match:
                json_str = json_match.group()
                logging.info(f"Extracted JSON: {json_str}")
                return json.loads(json_str)
            else:
                raise ValueError(f"No JSON found in agent response: {agent_response}")
                
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON from agent response: {e}")
        logging.error(f"Agent response was: {agent_response}")
        raise ValueError(f"Invalid JSON response from agent: {agent_response}")
    except Exception as e:
        logging.error(f"Failed to call Azure AI Agent: {e}")
        raise

def fallback_date_parser(user_query: str) -> dict:
    """Fallback date parser for common Spanish phrases when Azure AI Agent fails."""
    query_lower = user_query.lower().strip()
    today = datetime.now().date()
    
    if "mes pasado" in query_lower or "último mes" in query_lower:
        # Last month
        last_month = today.replace(day=1) - timedelta(days=1)
        start_of_last_month = last_month.replace(day=1)
        return {
            "start": start_of_last_month.isoformat(),
            "end": last_month.isoformat()
        }
    elif "semana pasada" in query_lower or "última semana" in query_lower:
        # Last week
        days_back = (today.weekday() + 1) % 7 + 6  # Go to previous Sunday, then back 6 more days
        start_of_last_week = today - timedelta(days=days_back)
        end_of_last_week = start_of_last_week + timedelta(days=6)
        return {
            "start": start_of_last_week.isoformat(),
            "end": end_of_last_week.isoformat()
        }
    elif "ayer" in query_lower:
        # Yesterday
        yesterday = today - timedelta(days=1)
        return {"date": yesterday.isoformat()}
    elif "hoy" in query_lower:
        # Today
        return {"date": today.isoformat()}
    else:
        # Try to extract year if present
        import re
        year_match = re.search(r'\b(20\d{2})\b', query_lower)
        if year_match:
            year = int(year_match.group(1))
            return {
                "start": f"{year}-01-01",
                "end": f"{year}-12-31"
            }
        
        # Default fallback - last month
        last_month = today.replace(day=1) - timedelta(days=1)
        start_of_last_month = last_month.replace(day=1)
        return {
            "start": start_of_last_month.isoformat(),
            "end": last_month.isoformat()
        }

def build_filter_expression(date_data: dict):
    if "date" in date_data:
        d = parse_date(date_data["date"]).date().isoformat()
        # Format as DateTimeOffset for Azure Search
        filter_expr = f"metadata_spo_item_release_date eq {d}T00:00:00Z"
        logging.info(f"Single date filter: {filter_expr}")
        return filter_expr
    elif "start" in date_data and "end" in date_data:
        start = parse_date(date_data["start"]).date().isoformat()
        end = parse_date(date_data["end"]).date().isoformat()
        # Format as DateTimeOffset for Azure Search
        filter_expr = f"(metadata_spo_item_release_date ge {start}T00:00:00Z and metadata_spo_item_release_date le {end}T23:59:59Z)"
        logging.info(f"Date range filter: {filter_expr}")
        return filter_expr
    return ""

def search_filtered_items(filter_string: str):
    payload = {
        "search": "*",
        "filter": filter_string,
        "top": 10
    }

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_KEY
    }

    logging.info(f"Search payload: {json.dumps(payload, indent=2)}")
    logging.info(f"Filter string: {filter_string}")

    try:
        response = requests.post(
            f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version=2023-07-01-preview",
            json=payload,
            headers=headers
        )
        
        if response.status_code != 200:
            logging.error(f"Azure Search API error: {response.status_code}")
            logging.error(f"Response content: {response.text}")
            response.raise_for_status()
            
        return response.json().get("value", [])
        
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error during search: {e}")
        logging.error(f"Response status: {response.status_code}")
        logging.error(f"Response content: {response.text}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error during search: {e}")
        raise

app = func.FunctionApp()

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        user_query = req.params.get("q")
        if not user_query:
            return func.HttpResponse("Missing 'q' parameter", status_code=400)

        logging.info(f"User query: {user_query}")

        # Step 1: Use Azure AI Agent to parse date(s)
        try:
            parsed_date_info = call_date_parser_agent(user_query)
            logging.info(f"Parsed date info from Azure AI Agent: {parsed_date_info}")
        except Exception as e:
            logging.warning(f"Azure AI Agent failed, using fallback parser: {e}")
            parsed_date_info = fallback_date_parser(user_query)
            logging.info(f"Parsed date info from fallback: {parsed_date_info}")

        # Step 2: Build filter
        filter_string = build_filter_expression(parsed_date_info)
        if not filter_string:
            return func.HttpResponse(
                json.dumps({"error": "No valid date or range detected."}),
                status_code=400,
                mimetype="application/json"
            )

        # Step 3: Search index
        results = search_filtered_items(filter_string)

        return func.HttpResponse(
            json.dumps({
                "parsed_dates": parsed_date_info,
                "filtered_items": results
            }, ensure_ascii=False),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.exception("Error in search_by_date")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
