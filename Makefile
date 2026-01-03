.PHONY: test test-verbose

# Run all pytest tests
test:
	docker compose -f docker-compose-development.yaml exec iroh-api pytest

# Run pytest with verbose output
test-verbose:
	docker compose -f docker-compose-development.yaml exec iroh-api pytest -v

# Run specific test file
# Usage: make test-file FILE=tests/test_order_types.py
test-file:
	docker compose -f docker-compose-development.yaml exec iroh-api pytest $(FILE) -v
