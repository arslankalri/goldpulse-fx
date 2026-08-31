const test = require('node:test');
const assert = require('node:assert/strict');
const { getSignalFromMetrics, computeRsi, buildSignalPayload } = require('./server');

test('buy signal is generated on bullish conditions', () => {
  const signal = getSignalFromMetrics({
    price: 2398,
    ma20: 2389,
    ma50: 2368,
    rsi: 64,
    sentiment: 0.22,
    volumeScore: 0.7
  });

  assert.equal(signal.label, 'BUY');
  assert.ok(signal.confidence >= 80);
});

test('sell signal is generated on bearish conditions', () => {
  const signal = getSignalFromMetrics({
    price: 2352,
    ma20: 2378,
    ma50: 2390,
    rsi: 38,
    sentiment: -0.25,
    volumeScore: 0.3
  });

  assert.equal(signal.label, 'SELL');
  assert.ok(signal.confidence >= 75);
});

test('computeRsi returns a valid value in the normal range', () => {
  const prices = [100, 101, 102, 101, 103, 104, 105, 104, 106, 108, 110, 109, 111, 113, 114, 112, 115, 117, 119, 118, 120];
  const value = computeRsi(prices, 14);
  assert.ok(value >= 0 && value <= 100);
});

test('gold payload uses Binance PAXGUSDT and never invents an unavailable quote', async () => {
  const payload = await buildSignalPayload();
  assert.equal(payload.symbol, 'PAXGUSDT');
  assert.ok(payload.price === null || Number.isFinite(payload.price));
  assert.ok(payload.signal === 'UNAVAILABLE' || ['BUY', 'SELL', 'WATCH'].includes(payload.signal));
});
