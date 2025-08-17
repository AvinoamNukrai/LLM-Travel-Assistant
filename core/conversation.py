"""
core/conversation.py

Conversation-first travel assistant with enhanced prompt engineering.
Focus on natural flow, chain-of-thought reasoning, and context management.
"""

from dataclasses import dataclass
from typing import Optional
from core.session import Session
from tools.weather import geocode_city, fetch_weather, summarize_weather


@dataclass
class ConversationState:
    """Track conversation context and user needs"""
    city: Optional[str] = None
    country: Optional[str] = None
    dates: Optional[str] = None
    interests: list[str] = None
    budget_level: Optional[str] = None
    travel_style: Optional[str] = None
    current_focus: Optional[str] = None
    
    def __post_init__(self):
        if self.interests is None:
            self.interests = []


def build_context_prompt(session: Session, user_input: str) -> str:
    """Build a comprehensive context-aware prompt using chain-of-thought reasoning"""
    
    # Extract current context
    state = extract_conversation_state(session)
    
    # Get weather data if available
    weather_context = ""
    if state.city and state.dates:
        weather_data = get_weather_context(state.city, state.dates)
        if weather_data:
            weather_context = f"\nWeather context: {weather_data}"
    
    # Build conversation history summary
    history_summary = summarize_recent_context(session)
    
    return f"""You are Navan, an expert travel planning assistant. You excel at natural, helpful conversations about travel.

CONTEXT ANALYSIS (think through this step by step):
{history_summary}

Current conversation state:
- Destination: {state.city or 'not specified'}
- Travel dates: {state.dates or 'not specified'}  
- Interests: {', '.join(state.interests) if state.interests else 'exploring'}
- Budget: {state.budget_level or 'not specified'}
- Travel style: {state.travel_style or 'not specified'}{weather_context}

REASONING PROCESS:
1. What is the user asking for in this message: "{user_input}"?
2. What information do I have vs what's missing?
3. How can I be most helpful while keeping the conversation natural?
4. Should I provide specific recommendations or ask a clarifying question?

RESPONSE GUIDELINES:
- Be conversational and warm, not robotic
- Provide actionable, specific advice when possible
- Use external data (weather) naturally in recommendations
- Ask ONE follow-up question only if critical info is missing
- Keep responses concise but helpful
- Remember: this is a conversation, not an interrogation

Your response:"""


def extract_conversation_state(session: Session) -> ConversationState:
    """Extract conversation state from session history"""
    state = ConversationState()
    
    # Simple extraction from slots if available
    if hasattr(session, 'slots'):
        state.city = session.slots.city
        state.country = session.slots.country
        if session.slots.start_date and session.slots.end_date:
            state.dates = f"{session.slots.start_date} to {session.slots.end_date}"
        elif session.slots.month:
            state.dates = f"month: {session.slots.month}"
    
    # Extract interests, budget, style from conversation
    full_text = " ".join([msg.get("content", "") for msg in session.history if msg.get("role") == "user"])
    
    # Interest extraction
    interest_keywords = {
        "history": ["history", "historical", "ancient", "ruins", "museum"],
        "food": ["food", "restaurant", "cuisine", "eat", "dining"],
        "art": ["art", "gallery", "painting", "sculpture"],
        "outdoor": ["outdoor", "park", "garden", "walking", "hiking"],
        "nightlife": ["nightlife", "bar", "club", "evening"],
        "family": ["family", "kids", "children", "stroller"]
    }
    
    for interest, keywords in interest_keywords.items():
        if any(kw in full_text.lower() for kw in keywords):
            state.interests.append(interest)
    
    # Budget extraction
    if any(word in full_text.lower() for word in ["budget", "cheap", "affordable"]):
        state.budget_level = "budget"
    elif any(word in full_text.lower() for word in ["luxury", "upscale", "high-end"]):
        state.budget_level = "luxury"
    
    return state


def summarize_recent_context(session: Session) -> str:
    """Summarize recent conversation for context"""
    if not session.history or len(session.history) < 2:
        return "This is the start of our conversation."
    
    recent = session.history[-4:]  # Last 4 messages
    summary_parts = []
    
    for msg in recent:
        role = msg.get("role", "")
        content = msg.get("content", "")[:100]  # Truncate long messages
        if role == "user":
            summary_parts.append(f"User asked: {content}")
        elif role == "assistant":
            summary_parts.append(f"I responded about: {content}")
    
    return "Recent conversation:\n" + "\n".join(summary_parts)


def get_weather_context(city: str, dates: str) -> Optional[str]:
    """Get weather context for the conversation"""
    try:
        # This would integrate with the existing weather tools
        # For now, return a placeholder that indicates weather integration
        return f"Weather data available for {city} during {dates}"
    except Exception:
        return None


def should_ask_clarifying_question(state: ConversationState, user_input: str) -> bool:
    """Decide if we need to ask for more information"""
    # Only ask if we're missing critical info AND user seems to want recommendations
    asking_for_recommendations = any(word in user_input.lower() for word in [
        "recommend", "suggest", "what should", "where to", "ideas", "help"
    ])
    
    missing_destination = not state.city
    missing_timeframe = not state.dates
    
    return asking_for_recommendations and (missing_destination or missing_timeframe)


def enhance_with_external_data(response: str, state: ConversationState) -> str:
    """Enhance response with relevant external data"""
    # This would integrate weather, local events, etc.
    # For now, return the response as-is
    return response
