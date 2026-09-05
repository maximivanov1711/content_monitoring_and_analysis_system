# Overview

This is a Russian content moderation system designed to automatically detect and analyze extremist, violent, and other prohibited content in Russian social media posts according to Russian Federation laws. The system performs comprehensive content monitoring across multiple social media platforms including TikTok, Instagram, YouTube, VK, Telegram, Twitch, and Dzen. It searches for content related to specific individuals (particularly "Арсен Маркарян"), extracts detailed post information, analyzes subtitles/transcripts, and identifies prohibited moments using AI-powered content analysis.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Pipeline Architecture
The system follows a modular pipeline architecture with five main processing stages:
1. **Search Stage** - Multi-platform content discovery using various APIs
2. **Add Info Stage** - Content enrichment and metadata extraction
3. **Add Subtitles Stage** - Media transcription and subtitle processing
4. **Analysis Stage** - AI-powered content moderation using OpenAI
5. **Export Stage** - Results formatting and delivery via webhooks

## Search Infrastructure
- **Multi-platform Support**: Integrates with Oxylabs for Google searches, Apify for VK/Instagram, custom APIs for YouTube/TikTok, Telemetr for Telegram
- **Query Management**: Flexible query configuration supporting multiple search parameters, date ranges, and filtering options
- **Rate Limiting**: Implements semaphore-based rate limiting with configurable delays per API endpoint
- **Result Deduplication**: URL-based duplicate removal across all search results

## Content Processing Architecture
- **Modular Processors**: Dedicated processors for each platform (Instagram, YouTube, TikTok, VK, Twitch, Dzen, Telegram)
- **Async Processing**: Full async/await implementation with configurable batch sizes and concurrency limits
- **Content Validation**: Multi-layered validation including profile exclusion lists and content quality checks
- **Media Handling**: Integrated media download and transcription capabilities using multiple APIs

## AI Analysis Framework
- **Structured Analysis**: Uses Pydantic models for consistent OpenAI API responses
- **Content Categorization**: Implements 7-category violation detection framework covering extremism, violence, discrimination, war content, politics, drugs/suicide, and destructive subcultures
- **Multilingual Support**: Specialized for Russian language content analysis with cultural context awareness
- **Batch Processing**: Staggered API calls with configurable delays to manage rate limits

## Data Storage Strategy
- **PostgreSQL Integration**: Async connection pooling using asyncpg for persistent storage
- **Local Caching**: JSON-based local storage for intermediate results and backups
- **Result Archiving**: Automatic file organization with timestamp-based naming and previous version management

## Notification and Export System
- **Webhook Integration**: N8N webhook endpoints for real-time notifications and data export
- **Batch Export**: Configurable batch sizes (500 records) for large result sets
- **Error Tracking**: Comprehensive error logging with unique error IDs and notification alerts

## Automation and Scheduling
- **Cron-based Scheduling**: APScheduler integration for automated task execution
- **Task Configuration**: JSON5-based task definitions with comprehensive parameter support
- **Graceful Shutdown**: Signal handling for clean termination and resource cleanup

## Security and Compliance Framework
- **Profile Filtering**: Maintains exclusion lists for official/friendly profiles and content editors
- **Content Scoring**: Multi-tier scoring system (0-2) based on keyword presence and relevance
- **Legal Compliance**: Specifically designed for Russian Federation content moderation laws

# External Dependencies

## Core APIs and Services
- **Oxylabs**: Primary web scraping service for Google searches and HTML content extraction
- **OpenAI GPT**: Content analysis and violation detection using structured prompts
- **Apify**: Multi-platform scrapers for VK, Instagram, TikTok, and general web scraping
- **Salad API**: Audio/video transcription service for media content analysis

## Social Media APIs
- **YouTube**: Custom API integration for video metadata, transcripts, and channel information
- **Telemetr**: Telegram channel monitoring and post extraction
- **TikTok API**: Video metadata and content extraction via RapidAPI
- **Instagram/VK**: Apify-powered content scrapers with rate limiting

## Infrastructure Services
- **PostgreSQL**: Primary database for persistent storage with connection pooling
- **N8N**: Webhook automation platform for notifications and data export
- **GitHub Gists**: Text content storage and sharing for large subtitle files
- **GoFile**: Media file hosting for transcription workflows

## Development and Monitoring
- **APScheduler**: Task scheduling and automation framework
- **Asyncpg**: High-performance PostgreSQL adapter for Python
- **Aiohttp**: Async HTTP client for API communications
- **Python-dotenv**: Environment variable management for API keys and configuration