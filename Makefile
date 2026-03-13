# Shortcuts: run "make tests", "make lint", etc. from project root.
# PYTHONPATH is set so config finds the project root; required by the app.

PYTHONPATH := $(CURDIR)
export PYTHONPATH

.PHONY: tests lint evaluation evaluation_report_cosine evaluation_report_l2 run_chatbot run_admin run_admin_api

tests:
	pytest tests/ -v

lint:
	ruff check .
	ruff format --check .

evaluation:
	python run_evaluation.py

evaluation_report_cosine:
	python run_evaluation.py -o evaluation_report_cosine.txt --remove-index

evaluation_report_l2:
	python run_evaluation.py -o evaluation_report_l2.txt --remove-index

run_chatbot:
	python run_chatbot_agent.py

run_admin:
	python run_admin_console_agent.py

run_admin_api:
	python run_admin_api.py
