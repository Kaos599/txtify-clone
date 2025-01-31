# 🌐 Txtify Clone - Web Content Extractor

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.29%2B-FF4B4B.svg)](https://streamlit.io)
[![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini-orange)](https://deepmind.google/technologies/gemini/)

An advanced web content extraction tool that uses AI to clean and format web content while preserving meaningful information.

# 🔄 Version History {IMPORTANT}

## V3 (Latest) (Not Tested Enough due to hitting RateLimits)
- Multi-page extraction support  
- Linked page discovery  
- Enhanced rate limit handling  
- Progress tracking improvements  

## V2
- Full AI implementation for content parsing  
- Navigation menu item detection  
- Agent-based extraction  

## V1
- Static implementation with basic AI parsing  
- Single page extraction  
- Simple content cleaning  

---

## 🚀 Features

- **AI-Powered Cleaning**: Uses Google Gemini for intelligent content processing
- **Multi-Page Support**: Extract content from linked pages automatically
- **Clean Output**: Removes ads, navigation elements, and clutter
- **Flexible Extraction**: Choose between single page or multi-page extraction
- **User-Friendly Interface**: Built with Streamlit for easy interaction
- **Rate Limit Handling**: Smart handling of API rate limits
- **Progress Tracking**: Real-time progress indicators
- **Download Support**: Export extracted content as text files

## 🛠️ Installation

```bash
# Clone the repository
git clone https://github.com/Kaos599/txtify-clone.git
cd txtify

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Add your GEMINI_API_KEY to .env file
```
# 📦 Requirements

- Python 3.8+
- Streamlit  
- BeautifulSoup4  
- Google Generative AI  
- Langchain  
- python-dotenv  
- requests  
- aiohttp  

# 🚦 Usage

```bash
streamlit run streamlitV1.py
streamlit run streamlitV2.py
streamlit run streamlitV3.py
```

## ⚙️ Configuration  

Create a `.env` file with your Google Gemini API key:  

```env
GEMINI_API_KEY=your_api_key_here
```
