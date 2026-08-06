(function() {
    const OriginalWebSocket = window.WebSocket;

    function CustomWebSocket(url, protocols) {
        const ws = protocols
            ? new OriginalWebSocket(url, protocols)
            : new OriginalWebSocket(url);

        // Wrap send() to intercept outgoing messages
        const originalSend = ws.send;
        ws.send = function(data) {
            window.postMessage({
                type: "WS_INTERCEPT",
                payload: { direction: "outgoing", url, data }
            }, "*");
            return originalSend.call(this, data);
        };

        // Wrap onmessage to intercept incoming messages
        ws.addEventListener("message", (event) => {
            window.postMessage({
                type: "WS_INTERCEPT",
                payload: { direction: "incoming", url, data: event.data }
            }, "*");
        });

        return ws;
    }

    // Copy static props (important for instanceof checks, etc.)
    CustomWebSocket.prototype = OriginalWebSocket.prototype;
    CustomWebSocket.OPEN = OriginalWebSocket.OPEN;
    CustomWebSocket.CLOSED = OriginalWebSocket.CLOSED;
    CustomWebSocket.CLOSING = OriginalWebSocket.CLOSING;
    CustomWebSocket.CONNECTING = OriginalWebSocket.CONNECTING;

    window.WebSocket = CustomWebSocket;
})();
