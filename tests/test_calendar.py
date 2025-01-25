import pytest
from unittest.mock import patch, MagicMock
import datetime
from llm_calendar import (
    parse_command,
    add_entry,
    lookup_events
)

def test_parse_command():
    # Test valid commands
    assert parse_command('add_entry("2024-01-20", "test event")') == (
        'add_entry',
        ['2024-01-20', 'test event'],
        {}
    )
    
    assert parse_command('lookup_events("2024-01-01", "2024-12-31")') == (
        'lookup_events',
        ['2024-01-01', '2024-12-31'],
        {}
    )
    
    # Test invalid commands
    assert parse_command('invalid command') is None
    assert parse_command('rm -rf /') is None


@patch('llm_calendar.sqlite_utils.Database')
def test_add_entry(mock_db):
    # Setup mock database
    mock_db_instance = MagicMock()
    mock_db.return_value = mock_db_instance
    mock_events = MagicMock()
    mock_db_instance.__getitem__.return_value = mock_events

    # Test basic event addition
    add_entry("2024-01-20", "Test Event")
    mock_events.insert.assert_called_with({
        "start_time": "2024-01-20",
        "end_time": "2024-01-20",
        "text": "Test Event",
        "people": "",
        "prompt": None
    })

    # Test event with people
    add_entry("2024-01-21", "Family Dinner", people=["mom", "dad"])
    mock_events.insert.assert_called_with({
        "start_time": "2024-01-21",
        "end_time": "2024-01-21",
        "text": "Family Dinner",
        "people": "mom, dad",
        "prompt": None
    })


@patch('llm_calendar.sqlite_utils.Database')
def test_lookup_events(mock_db, capsys):
    # Setup mock database
    mock_db_instance = MagicMock()
    mock_db.return_value = mock_db_instance
    
    # Mock query results
    mock_events = [
        {"start_time": "2024-01-20", "end_time": "2024-01-20", "text": "Event 1", "people": ""},
        {"start_time": "2024-01-21", "end_time": "2024-01-21", "text": "Event 2", "people": "Alice"},
        {"start_time": "2024-01-22", "end_time": "2024-01-24", "text": "Event 3", "people": ""}
    ]
    mock_db_instance.query.return_value = mock_events

    # Test basic lookup
    lookup_events("2024-01-20", "2024-01-22", fancy=False)
    captured = capsys.readouterr()
    assert "Event 1" in captured.out
    assert "Event 2" in captured.out
    assert "Event 3" in captured.out

    # Test people filter
    mock_db_instance.query.return_value = [mock_events[1]]  # Only return Event 2 for Alice
    lookup_events("2024-01-20", "2024-01-22", people=["Alice"], fancy=False)
    captured = capsys.readouterr()
    assert "Event 2" in captured.out
