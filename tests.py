import requests
import urllib.parse
import json
import sys

def test_search_by_date(query_string):
    """
    Test the search_by_date Azure Function with a given query string.
    Automatically URL-encodes the query string (replacing spaces with %20).
    """
    # Base URL for the Azure Function running locally
    base_url = "http://localhost:7071/api/search_by_date"
    
    # URL encode the query string (replaces spaces with %20)
    encoded_query = urllib.parse.quote(query_string)
    
    # Build the full URL
    full_url = f"{base_url}?q={encoded_query}"
    
    print(f"Original query: '{query_string}'")
    print(f"Encoded query: '{encoded_query}'")
    print(f"Full URL: {full_url}")
    print("-" * 60)
    
    try:
        # Make the HTTP GET request with longer timeout
        print("Making request... (this may take up to 60 seconds)")
        response = requests.get(full_url, timeout=60)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print("-" * 60)
        
        if response.status_code == 200:
            # Parse and pretty-print JSON response
            try:
                json_response = response.json()
                
                # Display parsed dates
                if "parsed_dates" in json_response:
                    print("Parsed Dates:")
                    print(json.dumps(json_response["parsed_dates"], indent=2, ensure_ascii=False))
                    print("-" * 40)
                
                # Display filtered items count (main focus)
                if "filtered_items" in json_response:
                    filtered_items = json_response["filtered_items"]
                    print(f"Number of filtered items found: {len(filtered_items)}")
                else:
                    print("No 'filtered_items' found in response.")
                
            except json.JSONDecodeError:
                print("Response (not JSON):")
                print(response.text)
        else:
            print(f"Error Response:")
            print(response.text)
            
    except requests.exceptions.Timeout as e:
        print(f"Request timed out after 60 seconds: {e}")
        print("Note: The Azure Function may still be processing. Check the function logs.")
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: {e}")
        print("Make sure the Azure Function is running locally with 'func start'")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    
    print("=" * 60)

def main():
    """Main function to run tests with predefined query strings."""
    
    # Test queries - you can modify these or add more
    test_queries = [
        "¿Cuánto fue la producción GROSS DESARROLLO (BOE) diaria (meta, real y porcentaje de cumplimiento) para el campo/contrato LA HOCHA el día 29 de abril?",
        #"¿Cuáles fueron los porcentajes de Contribución YTD [BOF] Gross el 23 de abril?",
        #"¿Cuánto fue la producción GROSS DESARROLLO (BOE) diaria (meta, real y porcentaje de cumplimiento) para el campo/contrato LA HOCHA en el mes de abril?",
        #"La semana pasada ¿De cuánto fue la producción bruta desarrollo (BOE) diaria antes de descontar regalías (meta, real y porcentaje de cumplimiento) para el campo/contrato SSJN1?",
        #"¿Cuáles fueron los porcentajes de Contribución YTD [BOF] Gross para la semana pasada?",
        #"¿Cuáles fueron los porcentajes de Contribución YTD [BOF] Gross para las últimas 2 semanas?"
    ]
    
    print("Testing Azure Function: search_by_date")
    print("=" * 60)
    
    # If a command line argument is provided, use it as the query
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        test_queries = [query]
        print(f"Using command line query: '{query}'")
        print("=" * 60)
    
    # Run tests for each query
    for i, query in enumerate(test_queries, 1):
        print("-" * 60)
        print("*" * 60)
        print(f"TEST {i}/{len(test_queries)}")
        test_search_by_date(query)
        print("*" * 60)
        print("-" * 60)

if __name__ == "__main__":
    main()