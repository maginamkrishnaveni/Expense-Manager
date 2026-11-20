"""
ExpenseIQ AI Agent
==================
A LangGraph-powered RAG agent that answers natural-language questions
about the user's expenses stored in the Django database.

Architecture
------------
1. Sync helper  -> pulls expense records from Django ORM into plain dicts
2. Chroma store -> embeds + indexes every expense so the LLM can retrieve them
3. LangGraph    -> a two-node graph: "retrieve" → "generate"
   The agent decides whether to answer from retrieval context or use
   its own knowledge for general financial questions.

Usage (called from views.py)
-----------------------------
    from .ai_agent import answer_question
    reply = answer_question(flat_id=1, user_name="Alice", question="...")
"""

import os
import json
from datetime import date

# ── LangChain / LangGraph ────────────────────────────────────
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.schema import Document
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Optional

# ── Django ORM (safe to import at module level in Django context) ─
from .models import Expense, SharedExpense, Contribution, Settlement


# ══════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db")

# ══════════════════════════════════════════════════════════════
#  DATA HELPERS
# ══════════════════════════════════════════════════════════════

def _expense_to_doc(expense: Expense) -> Document:
    """Convert a Django Expense ORM object into a LangChain Document."""
    content = (
        f"Personal expense: {expense.title} | "
        f"Amount: ₹{expense.amount} | "
        f"Category: {expense.category} | "
        f"Date: {expense.date} | "
        f"Note: {expense.note or 'none'}"
    )
    return Document(
        page_content=content,
        metadata={
            "type": "personal",
            "id": str(expense.id),
            "flat_id": str(expense.flat_id),
            "category": expense.category,
            "amount": expense.amount,
            "date": str(expense.date),
            "month": expense.date.month,
            "year": expense.date.year,
        },
    )


def _shared_to_doc(expense: SharedExpense) -> Document:
    """Convert a SharedExpense into a LangChain Document."""
    content = (
        f"Shared flat expense: {expense.title} | "
        f"Amount: ₹{expense.amount} | "
        f"Category: {expense.category} | "
        f"Date: {expense.date} | "
        f"Paid by: {expense.paid_by} | "
        f"From pool: {'yes' if expense.from_pool else 'no'} | "
        f"Note: {expense.note or 'none'}"
    )
    return Document(
        page_content=content,
        metadata={
            "type": "shared",
            "id": f"s{expense.id}",
            "flat_id": str(expense.flat_id),
            "category": expense.category,
            "amount": expense.amount,
            "date": str(expense.date),
            "month": expense.date.month,
            "year": expense.date.year,
        },
    )


def _load_flat_documents(flat_id: int) -> List[Document]:
    """Load all personal + shared expenses for a flat as Documents."""
    docs = []
    for e in Expense.objects.filter(flat_id=flat_id):
        docs.append(_expense_to_doc(e))
    for e in SharedExpense.objects.filter(flat_id=flat_id):
        docs.append(_shared_to_doc(e))
    return docs


def _flat_stats(flat_id: int) -> str:
    """Return a brief text summary of flat financials to inject as context."""
    today = date.today()
    personal = list(Expense.objects.filter(flat_id=flat_id))
    shared = list(SharedExpense.objects.filter(flat_id=flat_id))
    contributions = list(Contribution.objects.filter(flat_id=flat_id))

    personal_total = sum(e.amount for e in personal)
    shared_total = sum(e.amount for e in shared)
    this_month_personal = sum(
        e.amount for e in personal
        if e.date.month == today.month and e.date.year == today.year
    )
    this_month_shared = sum(
        e.amount for e in shared
        if e.date.month == today.month and e.date.year == today.year
    )
    total_contributions = sum(c.amount for c in contributions)

    cat_breakdown = {}
    for e in personal:
        cat_breakdown[e.category] = cat_breakdown.get(e.category, 0) + e.amount
    top_cat = max(cat_breakdown, key=cat_breakdown.get) if cat_breakdown else "None"

    return (
        f"Financial Summary for Flat ID {flat_id} (as of {today}):\n"
        f"- Total personal expenses ever: ₹{round(personal_total, 2)}\n"
        f"- Total shared/flat expenses ever: ₹{round(shared_total, 2)}\n"
        f"- This month personal spending: ₹{round(this_month_personal, 2)}\n"
        f"- This month shared spending: ₹{round(this_month_shared, 2)}\n"
        f"- Total contributions collected: ₹{round(total_contributions, 2)}\n"
        f"- Top spending category: {top_cat}\n"
        f"- Category breakdown: {json.dumps({k: round(v, 2) for k, v in cat_breakdown.items()})}"
    )


# ══════════════════════════════════════════════════════════════
#  CHROMA VECTOR STORE
# ══════════════════════════════════════════════════════════════

def _get_or_build_vectorstore(flat_id: int) -> Chroma:
    """
    Build or refresh the ChromaDB collection for this flat.
    Collection is named per-flat so multi-flat data stays isolated.
    """
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    collection_name = f"flat_{flat_id}_expenses"

    docs = _load_flat_documents(flat_id)
    if not docs:
        # Return an empty store if no data yet
        return Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=CHROMA_DIR,
        )

    # Rebuild store each call so it stays in sync with DB
    # For production: use incremental upserts instead
    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=CHROMA_DIR,
    )
    return vectorstore


# ══════════════════════════════════════════════════════════════
#  LANGGRAPH STATE + NODES
# ══════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    question: str
    flat_id: int
    user_name: str
    retrieved_docs: List[str]
    flat_stats: str
    answer: str


def retrieve_node(state: AgentState) -> AgentState:
    """Node 1: Retrieve relevant expense documents from ChromaDB."""
    try:
        vectorstore = _get_or_build_vectorstore(state["flat_id"])
        retriever = vectorstore.as_retriever(search_kwargs={"k": 6})
        docs = retriever.invoke(state["question"])
        state["retrieved_docs"] = [d.page_content for d in docs]
        state["flat_stats"] = _flat_stats(state["flat_id"])
    except Exception as e:
        state["retrieved_docs"] = []
        state["flat_stats"] = f"Error loading data: {e}"
    return state


def generate_node(state: AgentState) -> AgentState:
    """Node 2: Generate an answer using retrieved context + LLM."""
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.2,
        openai_api_key=OPENAI_API_KEY,
    )

    context = "\n".join(state["retrieved_docs"]) if state["retrieved_docs"] else "No expense records found."

    system_prompt = f"""You are ExpenseIQ Assistant, a smart financial advisor embedded in a household expense manager.
You help users understand their spending, find patterns, give budgeting tips, and answer questions about their expenses.

The user's name is: {state["user_name"]}

Here is a summary of their financial data:
{state["flat_stats"]}

Here are the most relevant expense records retrieved for this question:
{context}

Guidelines:
- Be concise and helpful. Use ₹ for currency.
- If asked about specific amounts, reference the data above.
- If the data doesn't have the answer, give general financial advice.
- Format numbers clearly. Use bullet points for lists.
- Keep responses under 200 words unless detailed analysis is requested."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["question"]),
    ]

    response = llm.invoke(messages)
    state["answer"] = response.content
    return state


# ══════════════════════════════════════════════════════════════
#  BUILD GRAPH
# ══════════════════════════════════════════════════════════════

def _build_graph():
    """Compile the two-node LangGraph: retrieve → generate → END."""
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


_GRAPH = None  # lazy-loaded singleton


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ══════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════

def answer_question(flat_id: int, user_name: str, question: str) -> str:
    """
    Main entry point. Given a flat ID, user name, and natural-language question,
    runs the LangGraph agent and returns a string answer.
    """
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-your"):
        return (
            "⚠️ AI Assistant is not configured. "
            "Please add your OPENAI_API_KEY to the .env file to enable this feature."
        )

    try:
        graph = _get_graph()
        initial_state: AgentState = {
            "question": question,
            "flat_id": flat_id,
            "user_name": user_name,
            "retrieved_docs": [],
            "flat_stats": "",
            "answer": "",
        }
        result = graph.invoke(initial_state)
        return result["answer"]
    except Exception as e:
        return f"Sorry, I encountered an error: {str(e)}"


def get_smart_insights(flat_id: int) -> List[dict]:
    """
    Returns a list of auto-generated spending insights for the dashboard.
    Each insight is {"icon": "...", "title": "...", "text": "..."}.
    """
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-your"):
        return []

    try:
        stats = _flat_stats(flat_id)
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.3,
            openai_api_key=OPENAI_API_KEY,
        )
        prompt = f"""Based on this expense data, generate exactly 3 short financial insights.
Return ONLY valid JSON array like:
[
  {{"icon": "bi-graph-up", "title": "Insight Title", "text": "One sentence insight."}},
  ...
]

Data:
{stats}

Use icons from Bootstrap Icons (bi-*). Keep each text under 20 words."""

        response = llm.invoke([HumanMessage(content=prompt)])
        insights = json.loads(response.content)
        return insights[:3]
    except Exception:
        return []
