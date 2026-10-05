import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        payload = json.loads(body)
        result = json.dumps({
            'id': 'smoke-test', 'object': 'chat.completion', 'created': 1,
            'model': payload['model'], 'choices': [{
                'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': 'Whakaora te patunga.'},
            }],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
        }).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(result)))
        self.end_headers()
        self.wfile.write(result)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
