# Fantasy Football Assistant (Fantacalcio)

## Overview

A comprehensive Italian fantasy football (fantacalcio) assistant application that provides AI-powered analysis, player recommendations, and transfer updates for Serie A. The system combines web scraping, knowledge management, and OpenAI integration to deliver accurate fantasy football insights.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Application Layer
- **Main Assistant**: `fantacalcio_assistant.py` serves as the primary orchestrator, handling user queries and coordinating between different components
- **Web Interface**: Flask-based web application providing user-friendly access to the assistant's capabilities
- **Configuration Management**: Centralized config system with environment variable support and `.env` file loading

### Knowledge Management System
- **ChromaDB Integration**: Vector database for storing and retrieving football-related knowledge using semantic search
- **RAG Pipeline**: Retrieval-Augmented Generation system combining document retrieval with OpenAI's language models
- **Embedding System**: Uses Sentence Transformers and HuggingFace models for text embeddings, with SQLite caching for performance
- **Corrections Management**: SQLite-based system for handling data corrections and maintaining data quality

### Data Collection & ETL
- **Apify Integration**: Professional web scraping solution for Transfermarkt data with anti-bot protection and rate limiting
- **Multiple ETL Pipelines**: Specialized scripts for different data sources (transfers, player info, team data)
- **Wikipedia Fallback**: Web fallback system for enriching player data from Wikipedia when primary sources are insufficient
- **Age Enrichment**: Specialized pipeline for extracting player birth years from various text sources

### Data Storage & Management
- **Roster Management**: JSON-based player roster with comprehensive metadata (prices, fantasy scores, appearances)
- **Entity Resolution**: Player and team name normalization with alias handling
- **Data Quality**: Automated systems for detecting and correcting obsolete or incorrect player information
- **Cache System**: Multi-layer caching for embeddings, web requests, and processed data

### Analytics & Intelligence
- **Player Analytics**: Statistical analysis for player efficiency, role performance, and value assessment
- **Match Tracking**: Fixture analysis and difficulty ratings for fantasy team optimization
- **Formation Optimization**: Budget-based formation suggestions for different league types
- **Rate Limiting**: Protection against API abuse in deployed environments

## External Dependencies

### AI & Machine Learning
- **OpenAI API**: GPT models for natural language processing and response generation
- **HuggingFace**: Sentence transformers for text embeddings and model hosting
- **ChromaDB**: Vector database for semantic search capabilities

### Web Scraping & Data
- **Apify**: Professional web scraping platform for Transfermarkt data extraction
- **Wikipedia API**: Fallback data source for player information enrichment
- **BeautifulSoup**: HTML parsing for web scraping tasks
- **Requests**: HTTP client for API calls and web requests

### Infrastructure
- **Flask**: Web framework for the user interface
- **SQLite**: Local database for corrections and caching
- **Replit**: Hosting platform with integrated secrets management

### Key Configuration
- Environment variables for API tokens (OpenAI, Apify, HuggingFace)
- ChromaDB path configuration for persistent storage
- Season filtering and reference year settings
- Rate limiting and deployment detection