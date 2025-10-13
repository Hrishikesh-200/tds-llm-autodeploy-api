# Read the doc: https://huggingface.co/docs/hub/spaces-sdks-docker# you will also find guides on how best to write your Dockerfile
FROM python:3.10

# Create a non-root user for security
RUN useradd -m -u 1000 user
USER user

# Set environment variables for the user's path
ENV PATH="/home/user/.local/bin:$PATH"

# Set the working directory
WORKDIR /app

# Copy and install Python dependencies
COPY --chown=user ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the application files
COPY --chown=user . /app

# Command to run the application using Uvicorn on port 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]