# MCP Server Guide

**How to use Claim Auditor as an MCP server for AI agents (Claude Code, Cursor, custom agents).**

The Model Context Protocol (MCP) allows AI agents to access Claim Auditor functionality as tools, enabling programmatic analysis of earnings call accuracy.

---

## Table of Contents

1. [What is MCP?](#1-what-is-mcp)
2. [Quick Start](#2-quick-start)
3. [Available Tools](#3-available-tools)
4. [Configuration](#4-configuration)
5. [Usage Examples](#5-usage-examples)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. What is MCP?

**Model Context Protocol (MCP)** is a standard for exposing tools and resources to AI agents.

### Why Use MCP?

Instead of manually running commands:
```bash
python -m scripts.run_pipeline --tickers AAPL
curl http://localhost:8000/api/companies/AAPL
```

AI agents can directly call:
```python
mcp.run_pipeline(tickers=["AAPL"])
mcp.analyze_company(ticker="AAPL")
```

### Use Cases

1. **AI-powered analysis** - "Analyze Amazon's earnings accuracy"
2. **Automated research** - "Find companies with rounding bias patterns"
3. **Conversational queries** - "Which company has the highest trust score?"
4. **Batch operations** - "Run pipeline for all tech companies"

---

## 2. Quick Start

### Prerequisites

- Python 3.13+ environment with dependencies installed
- API keys configured in `.env` file
- Claude Code or MCP-compatible AI client

### Step 1: Start MCP Server

```bash
cd claim-auditor/backend

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Start server
python mcp_server.py
```

**Output:**
```
MCP Server initialized
Available tools: list_companies, analyze_company, get_claims, ...
Listening for requests...
```

### Step 2: Configure AI Client

**For Claude Code:**

Add to `~/.config/claude-code/mcp_config.json`:
```json
{
  "mcpServers": {
    "claim-auditor": {
      "command": "/absolute/path/to/backend/.venv/bin/python",
      "args": ["/absolute/path/to/backend/mcp_server.py"],
      "env": {
        "FMP_API_KEY": "your_fmp_key",
        "ANTHROPIC_API_KEY": "your_anthropic_key"
      }
    }
  }
}
```

**For Cursor:**

Similar configuration in Cursor's MCP settings.

### Step 3: Test Connection

In Claude Code or your MCP client:
```
User: "List all companies in the claim auditor"
Agent: [Calls list_companies() tool]
Agent: "Found 3 companies: AAPL (99.8), MSFT (95.2), AMZN (87.4)"
```

---

## 3. Available Tools

### `list_companies()`

**Description:** Get all companies with trust scores.

**Parameters:** None

**Returns:**
```json
[
  {
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "trust_score": 99.8,
    "total_claims": 82,
    "verdict_breakdown": {
      "correct": 80,
      "mostly_correct": 1,
      "misleading": 0,
      "incorrect": 0,
      "unverifiable": 1
    }
  }
]
```

**Use case:** "Which companies have the lowest trust scores?"

---

### `analyze_company(ticker: str)`

**Description:** Full analysis for a specific company.

**Parameters:**
- `ticker` (required): Stock ticker symbol (e.g., "AAPL", "MSFT")

**Returns:**
```json
{
  "company": {
    "ticker": "AMZN",
    "name": "Amazon.com, Inc.",
    "trust_score": 87.4
  },
  "claims": [...],
  "patterns": [
    {
      "pattern_type": "consistent_rounding_up",
      "severity": 0.70,
      "description": "7 out of 10 inexact claims favor company"
    }
  ],
  "quarters_analyzed": ["Q1 2025", "Q2 2025", "Q3 2025"]
}
```

**Use case:** "Analyze Amazon's earnings accuracy and show any patterns."

---

### `get_claims(ticker: str, verdict: Optional[str] = None)`

**Description:** Get claims for a company, optionally filtered by verdict.

**Parameters:**
- `ticker` (required): Stock ticker symbol
- `verdict` (optional): Filter by verdict ("correct", "mostly_correct", "misleading", "incorrect", "unverifiable")

**Returns:**
```json
[
  {
    "id": 123,
    "claim_text": "Revenue grew 15% year-over-year",
    "speaker": "Andy Jassy",
    "stated_value": 15.0,
    "actual_value": 11.2,
    "verdict": "misleading",
    "accuracy": 0.747,
    "explanation": "Stated 15% but actual growth was 11.2% (25.3% error)"
  }
]
```

**Use case:** "Show me all misleading claims from Amazon."

---

### `compare_quarters(ticker: str)`

**Description:** Quarter-by-quarter trend analysis.

**Parameters:**
- `ticker` (required): Stock ticker symbol

**Returns:**
```json
{
  "ticker": "AAPL",
  "quarters": [
    {
      "period": "Q1 2025",
      "trust_score": 99.5,
      "total_claims": 20,
      "correct": 19,
      "misleading": 1
    },
    {
      "period": "Q2 2025",
      "trust_score": 100.0,
      "total_claims": 21,
      "correct": 21,
      "misleading": 0
    }
  ],
  "trend": "improving"
}
```

**Use case:** "Is Apple's accuracy improving or declining over time?"

---

### `get_discrepancy_patterns(ticker: str)`

**Description:** Get systematic bias patterns for a company.

**Parameters:**
- `ticker` (required): Stock ticker symbol

**Returns:**
```json
[
  {
    "pattern_type": "consistent_rounding_up",
    "severity": 0.70,
    "description": "7 out of 10 inexact claims round favorably",
    "affected_quarters": ["Q1 2025", "Q2 2025"],
    "examples": [
      {
        "claim": "Revenue was $170.8B",
        "actual": "$156.3B",
        "difference": "+9.3%"
      }
    ]
  }
]
```

**Use case:** "Does Microsoft show any systematic bias in their claims?"

---

### `run_pipeline(tickers: List[str], steps: Optional[List[str]] = None)`

**Description:** Execute the analysis pipeline for specified companies.

**Parameters:**
- `tickers` (required): List of ticker symbols
- `steps` (optional): Pipeline steps to run ("ingest", "extract", "verify", "analyze"). If omitted, runs all steps.

**Returns:**
```json
{
  "status": "success",
  "tickers_processed": ["AAPL", "MSFT"],
  "steps_completed": ["ingest", "extract", "verify", "analyze"],
  "duration_seconds": 145,
  "claims_extracted": 87,
  "claims_verified": 87,
  "patterns_detected": 3
}
```

**Use case:** "Add Tesla to the database and analyze it."

**Note:** This is a long-running operation (1-3 minutes) that makes API calls to Claude.

---

## 4. Configuration

### Environment Variables

The MCP server requires these environment variables:

```bash
# Required
FMP_API_KEY=your_fmp_api_key          # Financial data API
ANTHROPIC_API_KEY=your_anthropic_key  # Claude for extraction

# Optional
DATABASE_URL=sqlite:///./data/claim_auditor.db  # Database path
LOG_LEVEL=INFO                                   # Logging level
```

### MCP Client Configuration

**Claude Code:**

Location: `~/.config/claude-code/mcp_config.json`

```json
{
  "mcpServers": {
    "claim-auditor": {
      "command": "/Users/yourname/claim-auditor/backend/.venv/bin/python",
      "args": ["/Users/yourname/claim-auditor/backend/mcp_server.py"],
      "env": {
        "FMP_API_KEY": "your_key",
        "ANTHROPIC_API_KEY": "your_key",
        "DATABASE_URL": "sqlite:///./data/claim_auditor.db"
      }
    }
  }
}
```

**Important:** Use absolute paths, not relative paths or `~`.

### Verification

Test your configuration:

```bash
# In Claude Code
"Use the claim-auditor MCP server to list all companies"

# Expected response
"I've called the list_companies tool and found 3 companies: ..."
```

---

## 5. Usage Examples

### Example 1: Research Query

**User:** "Which company has the most misleading claims?"

**Agent actions:**
1. `list_companies()` → Get all companies
2. `get_claims(ticker="AMZN", verdict="misleading")` → Check Amazon
3. `get_claims(ticker="MSFT", verdict="misleading")` → Check Microsoft
4. Compare counts

**Response:** "Amazon has 8 misleading claims, the most of any company analyzed."

---

### Example 2: Deep Dive Analysis

**User:** "Analyze Apple's earnings accuracy in detail"

**Agent actions:**
1. `analyze_company(ticker="AAPL")` → Get full analysis
2. `compare_quarters(ticker="AAPL")` → Check trends
3. `get_discrepancy_patterns(ticker="AAPL")` → Look for patterns

**Response:** "Apple has a trust score of 99.8 with 80 correct claims out of 82. No systematic patterns detected. Accuracy improved from Q1 (99.5) to Q3 (100.0)."

---

### Example 3: Pattern Detection

**User:** "Find all companies with rounding bias"

**Agent actions:**
1. `list_companies()` → Get all companies
2. For each: `get_discrepancy_patterns(ticker)` → Check for patterns
3. Filter for "consistent_rounding_up" pattern

**Response:** "Found 1 company with rounding bias: Amazon (severity 0.70) - 7 out of 10 inexact claims favor the company."

---

### Example 4: Adding New Company

**User:** "Add Tesla to the database and analyze it"

**Agent actions:**
1. `run_pipeline(tickers=["TSLA"])` → Full pipeline (1-3 min)
2. `analyze_company(ticker="TSLA")` → Get results

**Response:** "Tesla added with trust score 91.2. Extracted 34 claims across 3 quarters. Detected 1 pattern: metric switching between GAAP and non-GAAP figures."

---

### Example 5: Comparative Analysis

**User:** "Compare accuracy between Amazon and Microsoft"

**Agent actions:**
1. `analyze_company(ticker="AMZN")` → Amazon analysis
2. `analyze_company(ticker="MSFT")` → Microsoft analysis
3. Compare trust scores, patterns

**Response:** "Microsoft (95.2) is more accurate than Amazon (87.4). Amazon shows consistent rounding up pattern (severity 0.70), Microsoft has no patterns detected."

---

## 6. Troubleshooting

### MCP Server Won't Start

**Error:** `ModuleNotFoundError: No module named 'app'`

**Solution:**
```bash
# Ensure you're in backend directory
cd backend

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### Claude Code Can't Connect

**Error:** "MCP server 'claim-auditor' not found"

**Solution:**
1. Check `mcp_config.json` syntax (valid JSON)
2. Use absolute paths (not `~/` or relative)
3. Verify Python path: `which python` in your venv
4. Restart Claude Code

**Debug:**
```bash
# Test server manually
python mcp_server.py

# Should see: "MCP Server initialized"
```

---

### API Key Errors

**Error:** `APIError: Invalid API key`

**Solution:**
1. Verify keys in `.env` file or `mcp_config.json`
2. FMP key: Test at https://financialmodelingprep.com/developer/docs/
3. Anthropic key: Test at https://console.anthropic.com

**Check keys:**
```bash
# In terminal
echo $FMP_API_KEY
echo $ANTHROPIC_API_KEY
```

---

### Database Locked

**Error:** `OperationalError: database is locked`

**Solution:**
SQLite doesn't support concurrent writes. Stop other processes:
```bash
# Check running processes
ps aux | grep claim

# Stop services
docker compose down  # If running in Docker
```

For production, use Postgres instead of SQLite.

---

### Pipeline Timeout

**Error:** `run_pipeline()` times out after 5 minutes

**Solution:**
Pipeline can take 1-3 minutes per company. For multiple companies:
```python
# Instead of
run_pipeline(tickers=["AAPL", "MSFT", "AMZN", "GOOGL"])  # 5-10 min

# Do sequential
run_pipeline(tickers=["AAPL"])  # 2 min
run_pipeline(tickers=["MSFT"])  # 2 min
```

---

### Empty Results

**Error:** `list_companies()` returns empty array

**Solution:**
Database is empty. Run pipeline first:
```bash
# Via CLI
python -m scripts.run_pipeline

# Or via MCP
run_pipeline(tickers=["AAPL", "MSFT", "AMZN"])
```

---

## Architecture

### How MCP Server Works

```
┌──────────────┐
│ AI Agent     │  "Analyze AAPL"
│ (Claude)     │
└──────┬───────┘
       │ MCP Protocol
       ▼
┌──────────────────────────────┐
│ mcp_server.py                │
│ - Exposes tools via MCP      │
│ - Translates requests        │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ PipelineFacade               │
│ - Same entry point as CLI/API│
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Services → Engines → Repos   │
│ - Core business logic        │
└──────────────────────────────┘
```

**Key insight:** MCP server uses the same `PipelineFacade` as CLI and API. No duplicate logic.

---

## Development

### Adding New MCP Tools

Edit `mcp_server.py`:

```python
@server.tool()
async def your_new_tool(param: str) -> dict:
    """Tool description for AI agent."""
    facade = get_facade()
    result = facade.your_method(param)
    return result
```

AI agents will automatically discover the new tool.

---

### Testing MCP Server

**Unit tests:**
```bash
pytest tests/unit/test_mcp_server.py
```

**Manual test:**
```python
# In Python REPL
from mcp_server import list_companies
result = await list_companies()
print(result)
```

---

## Best Practices

1. **Use descriptive queries** - "Analyze Apple" works better than "AAPL data"
2. **Be specific about filters** - "Show misleading claims" vs "Show claims"
3. **Handle long operations** - `run_pipeline()` takes time, be patient
4. **Check database first** - Use `list_companies()` before adding new ones
5. **Absolute paths in config** - MCP doesn't expand `~` or relative paths

---

## Resources

- **MCP Specification:** https://modelcontextprotocol.io
- **Claude Code MCP Docs:** https://docs.anthropic.com/claude-code/mcp
- **Example Servers:** https://github.com/modelcontextprotocol/servers

---

## For Developers

### Source Files

- `backend/mcp_server.py` - MCP server implementation (200 lines)
- `backend/app/facade.py` - Backend entry point (used by MCP, CLI, API)

### Dependencies

- `mcp` - Model Context Protocol library
- `anthropic` - Required by facade for LLM calls
- All standard claim-auditor dependencies

### Extending

To add new functionality:
1. Add method to `PipelineFacade` (shared with CLI/API)
2. Expose as MCP tool in `mcp_server.py`
3. Test with AI agent

MCP is just another interface to the same clean architecture.

---

**Quick Reference:**

```bash
# Start server
python mcp_server.py

# Configure Claude Code
~/.config/claude-code/mcp_config.json

# Test connection
"List all companies using claim-auditor MCP"
```
