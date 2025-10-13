<<<<<<< HEAD
# Use an official Python runtime as a parent image
FROM python:3.10

# Set the working directory in the container
WORKDIR /app

# Copy dependency files and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /app

# The port must be 7860 for standard Hugging Face Space deployments
EXPOSE 7860

# Command to run the FastAPI application
# main:app refers to the 'app' object in 'main.py'
=======
# Use an official Python runtime as a parent image
FROM python:3.10

# Set the working directory in the container
WORKDIR /app

# Copy dependency files and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /app

# The port must be 7860 for standard Hugging Face Space deployments
EXPOSE 7860

# Command to run the FastAPI application
# main:app refers to the 'app' object in 'main.py'
>>>>>>> 52580779a2ed91d4be40cf59f3c3405935a228fc
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]