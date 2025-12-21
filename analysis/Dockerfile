FROM python:3.12-slim

WORKDIR /app

# Install Docker CLI, iproute2 (for ss command), Trivy, and build tools for cmdstanpy/Prophet
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    iproute2 \
    # Build tools for cmdstanpy (Prophet dependency)
    build-essential \
    cmake && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-cli && \
    # Install Trivy
    TRIVY_VERSION=$(curl -s https://api.github.com/repos/aquasecurity/trivy/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/') && \
    curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin ${TRIVY_VERSION} && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    # Install cmdstan for Prophet (compiles Stan models)
    python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"

# Copy application code
COPY src/ ./src/

# Set environment variables
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8800

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8800"]
