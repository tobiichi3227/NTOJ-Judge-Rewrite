# NTOJ-Judge-Rewrite
## Quick Start
### With Docker

```bash
docker build -t ntioj-judge-rewrite .
docker run -d -p 2502:2502 ntioj-judge-rewrite
```
The server will be running at `http://localhost:2502`.

### Without Docker
#### Build the checker
```bash
cd src/default-checker
make
```

#### Run the server
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
./runserver.sh
```
The server will be running at `http://localhost:2502`.
