# llm-calendar

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/fergusfettes/llm-calendar/blob/main/LICENSE)

Use LLM to manage your calendar events using natural language

## Installation

Install this plugin in the same environment as [LLM](https://llm.datasette.io/).
```bash
llm install llm-calendar
```

## Usage

The calendar plugin allows you to manage calendar events using natural language. It uses your [default LLM model](https://llm.datasette.io/en/stable/setup.html#setting-a-custom-default-model) to interpret commands and queries.

Add events like this:
```bash
llm calendar "dentist on 5th May"
llm calendar "mom visiting next week for 3 days"
```

Query your calendar:
```bash
llm calendar "what events do I have next week?"
llm calendar "when is mom visiting?"
```

The plugin will automatically interpret dates relative to today, handle multi-day events, and track people mentioned in events.

### Commands

- `llm calendar [query]` - Add or query calendar events using natural language
- `llm calendar dump` - Display all events in the database
- `llm calendar query --no-fancy` - Query events without LLM-generated summaries

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:
```bash
cd llm-calendar
python3 -m venv venv
source venv/bin/activate
```

Install the dependencies and test dependencies:
```bash
pip install -e '.[test]'
```

To run the tests:
```bash
pytest
```
