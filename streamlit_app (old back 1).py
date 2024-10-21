from pyngrok import ngrok
from IPython.display import display, HTML
from openai import OpenAI
from PIL import Image
import subprocess
import time
import sys
import socket
import requests
import json
import os
import hashlib
import streamlit as st
import ipywidgets as widgets
import pandas as pd
import streamlit.components.v1 as components
import plotly.express as px

# Set a password for the application
PASSWORD = "ong_zi_an"

def check_credentials():
    """Returns True if the user had the correct password and a valid OpenAI API key."""

    def validate_credentials():
        """Checks whether the password and OpenAI API key are correct."""
        if hashlib.sha256(st.session_state["password"].encode()).hexdigest() == hashlib.sha256(PASSWORD.encode()).hexdigest():
            # Password is correct, now check the OpenAI API key
            client = OpenAI(api_key=st.session_state["openai_key"])
            try:
                # Attempt to use the API key
                client.models.list()
                st.session_state["credentials_correct"] = True
                st.session_state["api_key"] = st.session_state["openai_key"]  # Store the API key securely
                del st.session_state["password"]  # Don't store the password
                del st.session_state["openai_key"]  # Remove the temporary key storage
            except Exception:
                st.session_state["credentials_correct"] = False
                st.error("Invalid OpenAI API key")
        else:
            st.session_state["credentials_correct"] = False
            st.error("Incorrect password")

    if "credentials_correct" not in st.session_state:
        # First run, show inputs for password and API key
        st.text_input("Password", type="password", key="password")
        st.text_input("OpenAI API Key", type="password", key="openai_key")
        st.button("Submit", on_click=validate_credentials)
        return False
    elif not st.session_state["credentials_correct"]:
        # Credentials incorrect, show inputs again
        st.text_input("Password", type="password", key="password")
        st.text_input("OpenAI API Key", type="password", key="openai_key")
        st.button("Submit", on_click=validate_credentials)
        return False
    else:
        # Credentials correct
        return True

def create_app():
    if not check_credentials():
        return

    st.sidebar.title('Navigation')
    page = st.sidebar.radio('Go to', ['Home', 'About Us', 'Methodology'])

    if page == 'Home':
        home_page()
    elif page == 'About Us':
        about_us_page()
    elif page == 'Methodology':
        methodology_page()

def home_page():
    st.title('HDB Resale Price Query App')
    st.write(f"Running on: {socket.gethostbyname(socket.gethostname())}")

    # Add the disclaimer using st.expander
    with st.expander("IMPORTANT DISCLAIMER - Please Read", expanded=True):
        st.warning("""
        IMPORTANT NOTICE: This web application is a prototype developed for educational purposes only. The information provided here is NOT intended for real-world usage and should not be relied upon for making any decisions, especially those related to financial, legal, or healthcare matters.

        Furthermore, please be aware that the LLM may generate inaccurate or incorrect information. You assume full responsibility for how you use any generated output.

        Always consult with qualified professionals for accurate and personalized advice.
        """)

    # Function to fetch HDB data
    @st.cache_data
    def fetch_hdb_data():
        datasets = [
            {"id": "d_ebc5ab87086db484f88045b47411ebc5", "name": "1990-1999 (Approval)"},
            {"id": "d_43f493c6c50d54243cc1eab0df142d6a", "name": "2000-Feb 2012 (Approval)"},
            {"id": "d_2d5ff9ea31397b66239f245f57751537", "name": "Mar 2012-Dec 2014 (Registration)"},
            {"id": "d_ea9ed51da2787afaf8e51f827c304208", "name": "Jan 2015-Dec 2016 (Registration)"},
            {"id": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc", "name": "Jan 2017 onwards (Registration)"}
        ]

        all_data = []
        for dataset in datasets:
            url = f"https://data.gov.sg/api/action/datastore_search?resource_id={dataset['id']}&limit=1000"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                df = pd.DataFrame(data['result']['records'])
                df['dataset'] = dataset['name']
                all_data.append(df)

        return pd.concat(all_data, ignore_index=True)

    # Load data
    with st.spinner('Loading HDB data...'):
        hdb_data = fetch_hdb_data()
    st.success('Data loaded successfully!')

    # Data preprocessing
    hdb_data['month'] = pd.to_datetime(hdb_data['month'])
    hdb_data['year'] = hdb_data['month'].dt.year
    hdb_data['resale_price'] = pd.to_numeric(hdb_data['resale_price'], errors='coerce')

    # Year range slider
    min_year = int(hdb_data['year'].min())
    max_year = int(hdb_data['year'].max())
    year_range = st.slider('Select year range', min_year, max_year, (min_year, max_year))

    # Filter data based on year range
    filtered_data = hdb_data[(hdb_data['year'] >= year_range[0]) & (hdb_data['year'] <= year_range[1])]

    # Town selection
    towns = sorted(filtered_data['town'].unique())
    selected_town = st.selectbox('Select a town', ['All'] + list(towns))

    if selected_town != 'All':
        filtered_data = filtered_data[filtered_data['town'] == selected_town]

    # Calculate average price per year
    yearly_avg = filtered_data.groupby(['year', 'town'])['resale_price'].mean().reset_index()

    # Create line plot
    fig = px.line(yearly_avg, x='year', y='resale_price', color='town',
                  title=f'Average HDB Resale Price by Year {"for " + selected_town if selected_town != "All" else ""}')
    fig.update_layout(xaxis_title='Year', yaxis_title='Average Resale Price (SGD)')
    st.plotly_chart(fig)

    # Display overall average price
    avg_price = filtered_data['resale_price'].mean()
    st.write(f"Overall average price ({year_range[0]}-{year_range[1]}{', ' + selected_town if selected_town != 'All' else ''}): ${avg_price:.2f}")

    # User input
    user_input = st.text_input('Enter your question about HDB resale prices:')

    if user_input:
        try:
            # Prepare data summary for OpenAI
            data_summary = f"""
            Data Summary:
            - Year range: {year_range[0]} to {year_range[1]}
            - Selected town: {selected_town if selected_town != 'All' else 'All towns'}
            - Overall average price: ${avg_price:.2f}
            - Number of transactions: {len(filtered_data)}
            - Lowest price: ${filtered_data['resale_price'].min():.2f}
            - Highest price: ${filtered_data['resale_price'].max():.2f}
            """

            client = OpenAI(api_key=st.session_state["api_key"])

            def get_average_price(town, year):
                town_data = filtered_data[filtered_data['town'] == town] if town != 'All' else filtered_data
                year_data = town_data[town_data['year'] == year]
                return year_data['resale_price'].mean() if not year_data.empty else None

            def get_price_trend(town, start_year, end_year):
                town_data = filtered_data[filtered_data['town'] == town] if town != 'All' else filtered_data
                trend_data = town_data[(town_data['year'] >= start_year) & (town_data['year'] <= end_year)]
                yearly_trend = trend_data.groupby('year')['resale_price'].mean().to_dict()
                return yearly_trend

            tools = [
                {
                    "name": "get_average_price",
                    "description": "Get the average price for a specific town and year",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "town": {"type": "string"},
                            "year": {"type": "integer"}
                        },
                        "required": ["town", "year"]
                    }
                },
                {
                    "name": "get_price_trend",
                    "description": "Get the price trend for a town over a period",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "town": {"type": "string"},
                            "start_year": {"type": "integer"},
                            "end_year": {"type": "integer"}
                        },
                        "required": ["town", "start_year", "end_year"]
                    }
                }
            ]

            messages = [
                {"role": "system", "content": "You are an expert in Singapore's housing market, specialising in HDB resale flat prices. Provide concise, accurate answers based on the data summary provided. If the data doesn't support a definitive answer, say so."},
                {"role": "user", "content": f"""
                Data Summary:
                {data_summary}

                User Question: {user_input}

                Please answer the question based solely on the provided data summary. If the data is insufficient to answer accurately, explain why.
                """}
            ]
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                functions=tools,
                function_call="auto",
                temperature=0.3,
                max_tokens=150,
                top_p=0.95,
                frequency_penalty=0.5,
                presence_penalty=0.5
            )

            # Check if the model wants to call a function
            if response.choices[0].message.function_call:
                function_name = response.choices[0].message.function_call.name
                function_args = json.loads(response.choices[0].message.function_call.arguments)

                if function_name == "get_average_price":
                    result = get_average_price(function_args["town"], function_args["year"])
                elif function_name == "get_price_trend":
                    result = get_price_trend(function_args["town"], function_args["start_year"], function_args["end_year"])

                # Send the result back to the model for final response
                messages.append({"role": "function", "name": function_name, "content": str(result)})
                final_response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=150,
                    top_p=0.95,
                    frequency_penalty=0.5,
                    presence_penalty=0.5
                )
                ai_response = final_response.choices[0].message.content
            else:
                ai_response = response.choices[0].message.content

            st.write("AI Response:", ai_response)

            # Display recent average price
            recent_data = filtered_data[filtered_data['year'] >= 2020]
            if not recent_data.empty:
                recent_avg_price = recent_data['resale_price'].mean()
                st.write(f"Average price since 2020 ({selected_town if selected_town != 'All' else 'All towns'}): ${recent_avg_price:.2f}")

        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

def about_us_page():
    st.title('About Us')
    st.write("""
    Welcome to the HDB Resale Price Query App! We are a team of data enthusiasts and developers
    passionate about making housing data more accessible and understandable to the public.

    Our mission is to provide a user-friendly platform that allows anyone to explore and analyze
    HDB resale prices in Singapore. We believe that by making this information more accessible,
    we can help individuals make more informed decisions about housing.

    Key Features of Our App:
    1. Interactive Data Visualization: Explore HDB resale prices across different years and towns.
    2. AI-Powered Queries: Ask questions about the data and get intelligent responses.
    3. Up-to-date Information: We regularly update our database to ensure you have access to the latest information.

    This app was developed as an educational project and should not be used for making real-world financial decisions.
    Always consult with qualified professionals for accurate and personalized advice.

    We welcome your feedback and suggestions to improve our app. Thank you for using our service!
    """)

def methodology_page():
    st.title('Methodology')
    st.write("""
    Our HDB Resale Price Query App uses a combination of data analysis, visualization, and artificial intelligence
    to provide insights into HDB resale prices. Here's an overview of our methodology:

    1. Data Collection:
       - We source our data from data.gov.sg, which provides official HDB resale transaction data.
       - The data is collected from multiple datasets covering different time periods from 1990 to the present.

    2. Data Processing:
       - We combine all datasets into a single pandas DataFrame for easier analysis.
       - Data is cleaned and preprocessed to ensure consistency and accuracy.
       - We convert date strings to datetime objects and ensure all price data is in the correct numeric format.

    3. Data Visualization:
       - We use Plotly Express to create interactive line charts showing average resale prices over time.
       - Users can filter the data by year range and town to focus on specific areas of interest.

    4. AI-Powered Queries:
       - We utilize OpenAI's GPT-3.5-turbo model to provide intelligent responses to user queries.
       - The AI is provided with a summary of the relevant data to ensure accurate and context-aware responses.
       - We use function calling to allow the AI to request specific data calculations when needed.

    5. Real-time Calculations:
       - We perform real-time calculations on the filtered data to provide up-to-date statistics such as
         overall average prices and recent trends.

    6. Security:
       - We implement a basic authentication system to protect access to the app and the OpenAI API key.
       - User passwords are hashed for security.

    Limitations and Disclaimers:
    - This app is for educational purposes only and should not be used for making financial decisions.
    - The AI responses, while based on the provided data, may sometimes be inaccurate or inconsistent.
    - The data is limited to what is available from data.gov.sg and may not include the most recent transactions.

    We are committed to continuously improving our methodology and welcome any suggestions for enhancement.
    """)

    image_path = "/content/drive/My Drive/Colab Notebooks/Flowchart.PNG"
    try:
        image = Image.open(image_path)
        st.image(image, caption='Flowchart of our methodology', use_column_width=True)
    except FileNotFoundError:
        st.error(f"Image file not found: {image_path}")
    except Exception as e:
        st.error(f"Error loading image: {str(e)}")

if __name__ == "__main__":
    create_app()