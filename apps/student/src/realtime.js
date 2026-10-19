import { API_URL } from './api';

// Best-effort live updates. Consumers always refetch over REST when an event arrives
// or the socket reconnects, so missed or duplicate events never corrupt the UI.
// `getToken` is called on every (re)connect so a refreshed access token is picked up.
export function connectRealtime(getToken, onEvent) {
  let ws;
  let closed = false;
  let delay = 1000;
  let ping;

  const open = () => {
    if (closed) return; // a reconnect timer can fire after logout
    const token = getToken();
    if (!token) return;
    // The token goes in the first frame, not the URL, so it never lands in server logs.
    ws = new WebSocket(`${API_URL.replace(/^http/, 'ws')}/v1/realtime`);
    ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }));
    ws.onmessage = (e) => {
      let msg;
      try {
        msg = JSON.parse(e.data);
      } catch {
        return;
      }
      if (msg.type === 'hello') {
        delay = 1000;
        onEvent({ type: 'connected' });
        clearInterval(ping);
        ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000);
        return;
      }
      onEvent(msg);
    };
    ws.onclose = () => {
      clearInterval(ping);
      onEvent({ type: 'disconnected' });
      if (!closed) setTimeout(open, (delay = Math.min(delay * 2, 15000)));
    };
    ws.onerror = () => ws.close();
  };

  open();
  return () => {
    closed = true;
    clearInterval(ping);
    ws && ws.close();
  };
}
