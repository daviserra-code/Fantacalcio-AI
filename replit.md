# Fantasy Football Assistant (Fantacalcio)

## Overview

A comprehensive Italian fantasy football (fantacalcio) assistant application that provides AI-powered analysis, player recommendations, and transfer updates for Serie A. The system combines web scraping, knowledge management, and OpenAI integration to deliver accurate fantasy football insights.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Authentication & User Management
- **Replit Auth Integration**: OAuth2-based authentication system supporting Google, GitHub, X, Apple, and email/password login
- **User Models**: PostgreSQL-based user management with subscription tracking and pro features
- **Session Management**: Secure session handling with database storage for OAuth tokens
- **Subscription System**: Stripe integration for pro subscription billing and feature gating

### Core Application Layer
- **Main Assistant**: `fantacalcio_assistant.py` serves as the primary orchestrator, handling user queries and coordinating between different components
- **Dual Web Interface**: 
  - Authenticated routes (`routes.py`) for logged-in users with league management features
  - Legacy interface (`web_interface.py`) for general fantasy football analysis
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
- **PostgreSQL Database**: Primary database for user accounts, leagues, and subscription management
- **User League Persistence**: Individual league rules stored per-user in the database with JSON serialization
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

### Authentication & Payments
- **Replit Auth**: OAuth2 authentication provider with social login support
- **Stripe**: Payment processing for pro subscriptions and billing management
- **Flask-Login**: Session management for authenticated users
- **Flask-Dance**: OAuth integration for social authentication

### Infrastructure
- **Flask**: Web framework for the user interface
- **PostgreSQL**: Primary database for user data and league management
- **SQLAlchemy**: ORM for database operations
- **SQLite**: Local database for corrections and caching (legacy)
- **Replit**: Hosting platform with integrated secrets management

### Key Configuration
- Environment variables for API tokens (OpenAI, Apify, HuggingFace, Stripe)
- Database connection settings for PostgreSQL
- Authentication configuration for Replit Auth and session management
- ChromaDB path configuration for persistent storage
- Season filtering and reference year settings
- Rate limiting and deployment detection

## League Rule Management Features

### Pro Subscription Model
- **Free Tier**: Basic access with 1 league limit and standard rule templates
- **Pro Tier (€9.99/month)**: Unlimited leagues, document import, advanced customization
- **Feature Gating**: Server-side protection with `@require_pro` decorators on premium endpoints

### League Management Capabilities
- **Multiple Leagues**: Pro users can create and manage unlimited custom leagues
- **Rule Customization**: Comprehensive rule configuration including:
  - Budget and auction settings
  - Roster composition and formation rules
  - Scoring system with custom bonuses/penalties
  - Transfer windows and playoff configurations
- **Document Import**: Upload Word/PDF documents to automatically parse and import league rules
- **Export Features**: Download league rules as formatted text or JSON for sharing

### User Experience
- **Landing Page**: Unauthenticated users see feature overview and login prompts
- **Dashboard**: Authenticated users access league management interface
- **League Selector**: Pro users can switch between multiple configured leagues
- **Responsive Design**: Bootstrap-based UI optimized for desktop and mobile access