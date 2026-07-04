import TerminalConfig from '../config/TerminalConfig.js';

export class OrderRouter {
  constructor() {
    this.ws = null;
    this.workingOrders = new Map();
    this.orderSeqNum = 0;
    this.status = 'DISCONNECTED';
    this.onOrderUpdate = null;
    this.onFill = null;
  }

  connect(url) {
    const wsUrl = url || TerminalConfig.ORDER_PLANT_URL;
    this.ws = new WebSocket(wsUrl);
    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      this.status = 'CONNECTED';
      console.log('[NEXUS] Order plant connected');
    };

    this.ws.onmessage = (event) => {
      this._handleOrderResponse(event.data);
    };

    this.ws.onclose = () => {
      this.status = 'DISCONNECTED';
      console.warn('[NEXUS] Order plant disconnected');
    };

    this.ws.onerror = () => {
      this.status = 'ERROR';
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  submitMarketOrder(symbol, side, size) {
    const order = {
      type: 'NEW_ORDER',
      symbol: symbol || TerminalConfig.SYMBOL,
      side,
      order_type: 'MARKET',
      size,
      order_id: ++this.orderSeqNum,
      timestamp: Date.now(),
    };

    this._send(order);
    return order.order_id;
  }

  submitLimitOrder(symbol, side, price, size) {
    const order = {
      type: 'NEW_ORDER',
      symbol: symbol || TerminalConfig.SYMBOL,
      side,
      order_type: 'LIMIT',
      price,
      size,
      order_id: ++this.orderSeqNum,
      timestamp: Date.now(),
    };

    this.workingOrders.set(order.order_id, {
      order_id: order.order_id,
      price,
      side,
      size,
      status: 'PENDING',
    });

    this._send(order);
    return order.order_id;
  }

  cancelOrder(orderId) {
    const msg = {
      type: 'CANCEL_ORDER',
      order_id: orderId,
      timestamp: Date.now(),
    };

    this._send(msg);
  }

  modifyOrder(orderId, newPrice, newSize) {
    const existing = this.workingOrders.get(orderId);
    if (existing) {
      existing.price = newPrice;
      existing.size = newSize || existing.size;
    }

    const msg = {
      type: 'MODIFY_ORDER',
      order_id: orderId,
      new_price: newPrice,
      new_size: newSize,
      timestamp: Date.now(),
    };

    this._send(msg);
  }

  getWorkingOrders() {
    const result = [];
    for (const [id, order] of this.workingOrders) {
      result.push({ ...order });
    }
    return result;
  }

  _send(msg) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const encoded = JSON.stringify(msg);
      this.ws.send(encoded);
    } else {
      console.warn('[NEXUS] Order plant not connected, queuing order:', msg.type);
    }
  }

  _handleOrderResponse(data) {
    try {
      let msg;
      if (data instanceof ArrayBuffer) {
        const decoder = new TextDecoder();
        msg = JSON.parse(decoder.decode(data));
      } else {
        msg = JSON.parse(data);
      }

      switch (msg.type) {
        case 'ORDER_ACCEPTED':
          if (this.workingOrders.has(msg.order_id)) {
            this.workingOrders.get(msg.order_id).status = 'WORKING';
          }
          if (this.onOrderUpdate) this.onOrderUpdate(msg);
          break;

        case 'ORDER_FILLED':
          this.workingOrders.delete(msg.order_id);
          if (this.onFill) this.onFill(msg);
          break;

        case 'ORDER_CANCELLED':
          this.workingOrders.delete(msg.order_id);
          if (this.onOrderUpdate) this.onOrderUpdate(msg);
          break;

        case 'ORDER_MODIFIED':
          if (this.workingOrders.has(msg.order_id)) {
            const order = this.workingOrders.get(msg.order_id);
            order.price = msg.new_price || order.price;
            order.size = msg.new_size || order.size;
            order.status = 'WORKING';
          }
          if (this.onOrderUpdate) this.onOrderUpdate(msg);
          break;

        case 'ORDER_REJECTED':
          this.workingOrders.delete(msg.order_id);
          if (this.onOrderUpdate) this.onOrderUpdate(msg);
          break;
      }
    } catch (e) {
      console.error('[NEXUS] Order response parse error:', e);
    }
  }
}

let instance = null;

export function getOrderRouter() {
  if (!instance) {
    instance = new OrderRouter();
  }
  return instance;
}
