FROM ollama/ollama

# Pre-pull a model (e.g. mistral)
RUN /bin/bash -c "ollama serve & sleep 5 && ollama pull mistral"
