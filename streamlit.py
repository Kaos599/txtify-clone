import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

MIN_CONTENT_LENGTH = 50
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

st.set_page_config(
    page_title="Web Content Extractor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        /* Main container styling */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        /* Header styling */
        h1 {
            background: linear-gradient(45deg, #2b5876, #4e4376);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            padding: 0.5rem 0;
            font-size: 3rem !important;
            font-weight: 700 !important;
            margin-bottom: 2rem !important;
            text-align: center;
        }
        
        /* Subheader styling */
        .subheader {
            text-align: center;
            color: #666;
            margin-bottom: 2rem;
            font-size: 1.2rem;
        }
        
        /* Card-like container */
        .css-1r6slb0 {
            background-color: #f8f9fa;
            border-radius: 10px;
            padding: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        /* Input field styling */
        .stTextInput > div > div > input {
            border-radius: 5px;
            font-size: 1.1rem;
            padding: 0.5rem 1rem;
        }
        
        /* Button styling */
        .stButton > button {
            border-radius: 5px;
            padding: 0.5rem 2rem;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }
        
        /* Progress bar styling */
        .stProgress > div > div > div {
            background-color: #2b5876;
        }
        
        /* Download button styling */
        .stDownloadButton > button {
            background-color: #2b5876;
            color: white;
            border: none;
            padding: 0.5rem 2rem;
            border-radius: 5px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .stDownloadButton > button:hover {
            background-color: #4e4376;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }
        
        /* Content container styling */
        .content-container {
            background-color: white;
            border-radius: 10px;
            padding: 2rem;
            margin: 2rem 0;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }
        
        /* Footer styling */
        .footer {
            text-align: center;
            padding: 2rem 0;
            color: #666;
            font-size: 0.9rem;
        }
    </style>
""", unsafe_allow_html=True)

def clean_text(text: str) -> str:
    """Clean extracted text by removing extra whitespace and unnecessary characters."""

    text = re.sub(r'\s+', ' ', text)

    text = re.sub(r'[^\w\s.,!?-]', '', text)

    text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
    return text.strip()

async def clean_with_genai(text: str) -> str:
    """Use Gemini Flash to filter out unnecessary content and improve readability."""
    try:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        
        generation_config = {
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 32,
            "max_output_tokens": 8192,
        }

        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-exp",
            generation_config=generation_config,
        )

        prompt = f"""CLEANING TASK: Clean and format the following web content while:
1. Removing navigation elements, headers, footers, and ads
2. Preserving all meaningful content
3. Maintaining proper paragraph structure
4. Keeping important headings and subheadings
5. Ensuring readability

CONTENT TO CLEAN:
{text}

CLEANED OUTPUT:"""

        response = model.generate_content(prompt)
        
        if "provide the actual scraped content" in response.text.lower():
            return "CONTENT EXTRACTION ERROR: Failed to retrieve meaningful page content"
            
        return response.text

    except Exception as e:
        return f"CLEANING ERROR: {str(e)}"

async def extract_content(url: str, progress_bar) -> tuple:
    """Extract content from a webpage using BeautifulSoup."""
    try:

        progress_bar.progress(0.2)
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(url, headers=HEADERS, timeout=10))
        response.raise_for_status()
        
        progress_bar.progress(0.4)
        

        soup = BeautifulSoup(response.text, 'html.parser')
        

        for element in soup.find_all(['script', 'style', 'nav', 'footer', 'iframe']):
            element.decompose()
            
        progress_bar.progress(0.6)
        
        main_content = None
        
        content_selectors = [
            'main',
            'article',
            '.content',
            '#content',
            '.post-content',
            '.entry-content',
            'body'
        ]
        
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                main_content = content.get_text(separator='\n', strip=True)
                break
                
        if not main_content:
            main_content = soup.body.get_text(separator='\n', strip=True)
            
        cleaned_text = clean_text(main_content)
        
        progress_bar.progress(0.8)
        

        if len(cleaned_text) < MIN_CONTENT_LENGTH:
            return False, "Error: Insufficient content extracted"
            
        final_clean = await clean_with_genai(cleaned_text)
        
        progress_bar.progress(1.0)
        
        return True, final_clean
        
    except requests.RequestException as e:
        return False, f"Error fetching the webpage: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def main():
    st.markdown("<h1>✨ Web Content Extractor</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='subheader'>Transform any webpage into clean, readable content</p>",
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        url = st.text_input(
            "Enter website URL:",
            placeholder="https://example.com",
            help="Paste the URL of any webpage you want to extract content from"
        )

        if st.button("🔍 Extract Content", type="primary", use_container_width=True):
            if url:
                if not url.startswith(('http://', 'https://')):
                    url = f'https://{url}'
                    
                with st.container():
                    progress_bar = st.progress(0)
                    st.markdown("### 🔄 Processing...")
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    success, result = loop.run_until_complete(extract_content(url, progress_bar))
                    loop.close()
                    
                    if success:
                        st.markdown("<h3 style='color: #2b5876;'>📑 Extracted Content:</h3>", unsafe_allow_html=True)
                        
                        st.markdown("<div class='content-container'>", unsafe_allow_html=True)
                        st.markdown(result)
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        btn_col1, btn_col2, btn_col3 = st.columns([1, 2, 1])
                        
                        with btn_col2:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            domain = url.split('//')[-1].split('/')[0].replace('.', '_')
                            filename = f"{domain}_{timestamp}.txt"
                            
                            st.download_button(
                                label="⬇️ Download as Text File",
                                data=result,
                                file_name=filename,
                                mime="text/plain",
                                use_container_width=True
                            )
                    else:
                        st.error(result)
            else:
                st.warning("⚠️ Please enter a URL")

    st.markdown("---")
    st.markdown("<h3 style='text-align: center; color: #2b5876;'>✨ Features</h3>", unsafe_allow_html=True)
    
    feat_col1, feat_col2, feat_col3 = st.columns(3)
    
    with feat_col1:
        st.markdown("""
            ### 🎯 Clean Content
            - Removes ads and clutter
            - Preserves important content
            - Maintains readability
        """)
    
    with feat_col2:
        st.markdown("""
            ### 🚀 Fast & Efficient
            - Quick extraction
            - AI-powered cleaning
            - Instant downloads
        """)
    
    with feat_col3:
        st.markdown("""
            ### 🛡️ Simple & Secure
            - Easy to use
            - No registration needed
        """)

    st.markdown("---")
    st.markdown(
        "<div class='footer'>Made with ❤️ by Harsh Dayal for Truxt.ai | © 2025</div>",
        unsafe_allow_html=True
    )

if __name__ == '__main__':
    main()