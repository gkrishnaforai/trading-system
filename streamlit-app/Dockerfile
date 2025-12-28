FROM python:3.11-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY streamlit-app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY streamlit-app/app.py .
COPY streamlit-app/api_client.py .
COPY streamlit-app/utils.py .
COPY streamlit-app/shared_functions.py .
COPY streamlit-app/testbed.py .
COPY streamlit-app/testbed_workflow.py .
COPY streamlit-app/pages/ ./pages/

# Check Python syntax before finalizing image
RUN python3 -c "import ast, sys, glob; [ast.parse(open(f).read()) for f in glob.glob('*.py') + glob.glob('pages/*.py')]" || (echo "❌ Python syntax errors found! Fix before building." && exit 1)

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

