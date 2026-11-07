import sys
import zmq

def ping(timeout_ms: int = 2000) -> int:
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.LINGER, 0)
    poller = zmq.Poller()
    poller.register(sock, zmq.POLLIN)

    try:
        sock.connect("tcp://127.0.0.1:47005")
        sock.send_json({"cmd": "ping"})

        socks = dict(poller.poll(timeout_ms))
        if socks.get(sock) == zmq.POLLIN:
            resp = sock.recv_json(flags=zmq.NOBLOCK)
            if resp.get("status") == "ok":
                print(f"CosyVoice ONLINE: {resp.get('engine')} on {resp.get('device')}")
                return 0
    except Exception:
        pass
    finally:
        sock.close(linger=0)
        ctx.term()

    return 1

if __name__ == "__main__":
    sys.exit(ping())
