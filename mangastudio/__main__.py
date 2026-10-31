import argparse
import threading
import webbrowser
import uvicorn


def main():
    parser = argparse.ArgumentParser(description='Lokale Manga-Werkstatt')
    parser.add_argument('--port', type=int, default=8042)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not args.no_browser:
        threading.Timer(1.7, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    uvicorn.run('mangastudio.web:app', host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
