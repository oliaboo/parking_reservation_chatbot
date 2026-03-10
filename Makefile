# Shortcuts: run "make tests", "make lint", etc. from project root.

.PHONY: tests lint evaluation run

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

run:
	python run.py
