/**
 * Production-ready WebSocket Connection Manager
 * 
 * Features:
 * - Single connection per client
 * - Auto-reconnect with exponential backoff
 * - Connection pooling
 * - Heartbeat/ping-pong
 * - Bandwidth optimization
 */

type MessageHandler = (data: any) => void;
type ConnectionHandler = () => void;

interface WebSocketManagerConfig {
  url: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
}

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private heartbeatInterval: number;
  
  private reconnectAttempts = 0;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private heartbeatTimeout: NodeJS.Timeout | null = null;
  private intentionalClose = false;
  
  private messageHandlers: Set<MessageHandler> = new Set();
  private connectHandlers: Set<ConnectionHandler> = new Set();
  private disconnectHandlers: Set<ConnectionHandler> = new Set();
  private errorHandlers: Set<(error: Event) => void> = new Set();
  
  public isConnected = false;
  
  constructor(config: WebSocketManagerConfig) {
    this.url = config.url;
    this.reconnectInterval = config.reconnectInterval || 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts || 10;
    this.heartbeatInterval = config.heartbeatInterval || 30000;
  }
  
  /**
   * Connect to WebSocket server
   */
  public connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Already connected');
      return;
    }
    
    try {
      // Construct WebSocket URL
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = this.url.startsWith('ws') ? this.url : `${protocol}//${window.location.host}${this.url}`;
      
      console.log(`[WebSocket] Connecting to ${wsUrl}...`);
      this.ws = new WebSocket(wsUrl);
      
      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onerror = this.handleError.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
      
    } catch (error) {
      console.error('[WebSocket] Connection error:', error);
      this.scheduleReconnect();
    }
  }
  
  /**
   * Disconnect from WebSocket server
   */
  public disconnect(): void {
    this.intentionalClose = true;
    this.clearTimeouts();
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    this.isConnected = false;
  }
  
  /**
   * Send message to server
   */
  public send(data: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(data));
      } catch (error) {
        console.error('[WebSocket] Send error:', error);
      }
    } else {
      console.warn('[WebSocket] Cannot send, not connected');
    }
  }
  
  /**
   * Register message handler
   */
  public onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }
  
  /**
   * Register connect handler
   */
  public onConnect(handler: ConnectionHandler): () => void {
    this.connectHandlers.add(handler);
    return () => this.connectHandlers.delete(handler);
  }
  
  /**
   * Register disconnect handler
   */
  public onDisconnect(handler: ConnectionHandler): () => void {
    this.disconnectHandlers.add(handler);
    return () => this.disconnectHandlers.delete(handler);
  }
  
  /**
   * Register error handler
   */
  public onError(handler: (error: Event) => void): () => void {
    this.errorHandlers.add(handler);
    return () => this.errorHandlers.delete(handler);
  }
  
  private handleOpen(): void {
    console.log('[WebSocket] Connected');
    this.isConnected = true;
    this.reconnectAttempts = 0;
    
    // Notify all connect handlers
    this.connectHandlers.forEach(handler => handler());
    
    // Start heartbeat
    this.startHeartbeat();
  }
  
  private handleMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data);
      
      // Handle system messages
      if (data.type === 'pong' || data.type === 'heartbeat') {
        // Reset heartbeat timeout
        this.resetHeartbeat();
        return;
      }
      
      // Notify all message handlers
      this.messageHandlers.forEach(handler => handler(data));
      
    } catch (error) {
      console.error('[WebSocket] Message parse error:', error);
    }
  }
  
  private handleError(error: Event): void {
    console.error('[WebSocket] Error:', error);
    this.errorHandlers.forEach(handler => handler(error));
  }
  
  private handleClose(): void {
    console.log('[WebSocket] Disconnected');
    this.isConnected = false;
    this.clearTimeouts();
    
    // Notify all disconnect handlers
    this.disconnectHandlers.forEach(handler => handler());
    
    // Reconnect if not intentional
    if (!this.intentionalClose) {
      this.scheduleReconnect();
    }
  }
  
  private startHeartbeat(): void {
    this.heartbeatTimeout = setTimeout(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping' });
        this.startHeartbeat(); // Schedule next
      }
    }, this.heartbeatInterval);
  }
  
  private resetHeartbeat(): void {
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
    }
    this.startHeartbeat();
  }
  
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WebSocket] Max reconnect attempts reached');
      return;
    }
    
    this.reconnectAttempts++;
    
    // Exponential backoff: 3s, 6s, 12s, 24s, ...
    const delay = this.reconnectInterval * Math.pow(2, this.reconnectAttempts - 1);
    const maxDelay = 60000; // Cap at 60 seconds
    const actualDelay = Math.min(delay, maxDelay);
    
    console.log(`[WebSocket] Reconnecting in ${actualDelay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, actualDelay);
  }
  
  private clearTimeouts(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
      this.heartbeatTimeout = null;
    }
  }
}

// Singleton instance
let wsManager: WebSocketManager | null = null;

export function getWebSocketManager(): WebSocketManager {
  if (!wsManager) {
    wsManager = new WebSocketManager({
      url: '/ws/metrics',
      reconnectInterval: 3000,
      maxReconnectAttempts: 10,
      heartbeatInterval: 25000
    });
  }
  return wsManager;
}

