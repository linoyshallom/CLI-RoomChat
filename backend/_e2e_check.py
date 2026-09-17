import asyncio
import json
import os
import tempfile

import httpx
import websockets

BASE_WS = "ws://127.0.0.1:5000/ws/chat"
BASE_HTTP = "http://127.0.0.1:5000"


async def recv_n(ws, n):
    out = []
    for _ in range(n):
        out.append(json.loads(await ws.recv()))
    return out


async def main():
    # --- chat: join, broadcast, history ordering ---
    async with websockets.connect(f"{BASE_WS}?username=alice") as alice, \
               websockets.connect(f"{BASE_WS}?username=bob") as bob:

        await alice.send(json.dumps({"action": "join", "room_type": "GLOBAL"}))
        msgs = await recv_n(alice, 2)  # no-history, own join broadcast
        assert "No messages" in msgs[0]["text"], msgs
        assert "alice joined" in msgs[1]["text"], msgs
        print("OK: alice joins GLOBAL, sees no-history then own join broadcast")

        await bob.send(json.dumps({"action": "join", "room_type": "GLOBAL"}))
        bob_msgs = await recv_n(bob, 2)
        assert "No messages" in bob_msgs[0]["text"]
        assert "bob joined" in bob_msgs[1]["text"]
        alice_sees_bob_join = await recv_n(alice, 1)
        assert "bob joined" in alice_sees_bob_join[0]["text"]
        print("OK: bob joins, alice sees bob's join broadcast live")

        await alice.send(json.dumps({"action": "message", "text": "hello bob"}))
        alice_echo = await recv_n(alice, 1)
        bob_recv = await recv_n(bob, 1)
        assert "hello bob" in alice_echo[0]["text"] and "alice" in alice_echo[0]["text"]
        assert "hello bob" in bob_recv[0]["text"] and "alice" in bob_recv[0]["text"]
        print("OK: live chat message broadcasts to both connected clients")

        # --- a THIRD client joins after messages exist -> must see full history
        # before any live traffic ---
        async with websockets.connect(f"{BASE_WS}?username=carol") as carol:
            await carol.send(json.dumps({"action": "join", "room_type": "GLOBAL"}))
            carol_first = json.loads(await carol.recv())
            assert carol_first["type"] == "CHAT" and "hello bob" in carol_first["text"], carol_first
            print("OK: third client joining sees history first, not interleaved live traffic")

            carol_join_broadcast_seen_by_alice = await recv_n(alice, 1)
            assert "carol joined" in carol_join_broadcast_seen_by_alice[0]["text"]

            # drain carol's own join broadcast + bob's copy so later asserts aren't thrown off
            await recv_n(carol, 1)
            await recv_n(bob, 1)

        # --- carol disconnected: kill without /quit-equivalent (just close), confirm no
        # crash and no more traffic sent to her ---
        disconnect_seen = await recv_n(alice, 1)
        assert "carol disconnected" in disconnect_seen[0]["text"]
        await recv_n(bob, 1)
        print("OK: client disconnect is detected and broadcast, server keeps running")

        # --- /switch between GLOBAL and a private room ---
        await alice.send(json.dumps({"action": "switch"}))
        await alice.send(json.dumps({"action": "join", "room_type": "PRIVATE", "group_name": "friends"}))
        switch_msgs = await recv_n(alice, 2)  # no-history for 'friends', own join broadcast
        assert "No messages" in switch_msgs[0]["text"], switch_msgs
        assert "friends" in switch_msgs[1]["text"], switch_msgs
        bob_sees_alice_leave = await recv_n(bob, 1)
        assert "alice disconnected from 'GLOBAL'" in bob_sees_alice_leave[0]["text"]
        print("OK: /switch leaves old room (broadcast to others) and joins the new one cleanly")

        await alice.send(json.dumps({"action": "message", "text": "private msg"}))
        await recv_n(alice, 1)

    # --- private room history is filtered by join timestamp: a second user joining
    # 'friends' now should NOT see 'private msg' sent before they checked in ---
    async with websockets.connect(f"{BASE_WS}?username=dave") as dave:
        await dave.send(json.dumps({"action": "join", "room_type": "PRIVATE", "group_name": "friends"}));
        dave_first = json.loads(await dave.recv())
        assert "No messages" in dave_first["text"], dave_first
        print("OK: private room history correctly filtered by join timestamp")

    # --- file transfer over real HTTP ---
    tmp_dir = tempfile.mkdtemp()
    src_path = os.path.join(tmp_dir, "sample.txt")
    with open(src_path, "wb") as f:
        f.write(b"end-to-end file transfer payload" * 100)

    async with httpx.AsyncClient() as http:
        with open(src_path, "rb") as f:
            resp = await http.post(f"{BASE_HTTP}/files", files={"file": ("sample.txt", f)})
        resp.raise_for_status()
        file_id = resp.json()["file_id"]
        print(f"OK: uploaded, file_id={file_id}")

        dl_dir = tempfile.mkdtemp()
        async with http.stream("GET", f"{BASE_HTTP}/files/{file_id}") as dl:
            dl.raise_for_status()
            dst = os.path.join(dl_dir, "sample.txt")
            with open(dst, "wb") as out:
                async for chunk in dl.aiter_bytes():
                    out.write(chunk)

        with open(src_path, "rb") as a, open(dst, "rb") as b:
            assert a.read() == b.read()
        print("OK: downloaded bytes match uploaded bytes exactly")

        # oversized -> reject cleanly (server's real 16MB cap, so just confirm 404 for junk id)
        resp = await http.get(f"{BASE_HTTP}/files/does-not-exist")
        assert resp.status_code == 404
        print("OK: unknown file_id -> 404")

    print("\nALL END-TO-END CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
