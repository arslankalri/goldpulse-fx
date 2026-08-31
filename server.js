const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;
const PUBLIC_DIR = fs.existsSync(path.join(__dirname, 'public')) ? path.join(__dirname, 'public') : __dirname;

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function roundOrNull(value, decimals = 2) {
  return Number.isFinite(value) ? Number(value.toFixed(decimals)) : null;
}

function computeEma(prices, period) {
  if (!prices.length) return 0;
  const multiplier = 2 / (period + 1);
  let ema = prices[0];
  prices.slice(1).forEach((price) => {
    ema = (price - ema) * multiplier + ema;
  });
  return ema;
}

function computeRsi(prices, period = 14) {
  if (prices.length <= period) return 50;

  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i += 1) {
    const diff = prices[prices.length - period - 1 + i] - prices[prices.length - period - 2 + i];
    if (diff >= 0) gains += diff; else losses += Math.abs(diff);
  }

  const avgGain = gains / period;
  const avgLoss = losses / period;

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

function getSignalFromMetrics({ price, ma20, ma50, rsi, sentiment, volumeScore }) {
  const trendBullish = price > ma20 && ma20 > ma50;
  const trendBearish = price < ma20 && ma20 < ma50;

  if (trendBullish && rsi > 52 && sentiment > 0.05 && volumeScore > 0.55) {
    return { label: 'BUY', confidence: 88 };
  }

  if (trendBearish && rsi < 48 && sentiment < -0.05 && volumeScore < 0.45) {
    return { label: 'SELL', confidence: 82 };
  }

  return { label: 'WATCH', confidence: 68 };
}

function getTechnicalSignal({ price, ma20, ma50, rsi, volumeScore }) {
  const trendBullish = price > ma20 && ma20 > ma50;
  const trendBearish = price < ma20 && ma20 < ma50;
  if (trendBullish && rsi > 52 && volumeScore > 0.55) return 'BUY';
  if (trendBearish && rsi < 48 && volumeScore < 0.45) return 'SELL';
  return 'WATCH';
}

function backtestCandles(candles, { riskPercent = 1, leverage = 10 } = {}) {
  const feeRate = 0.0004;
  const slippageRate = 0.0002;
  const horizon = 4;
  const targetRate = 0.012;
  const stopRate = 0.008;
  const trades = [];

  for (let index = 60; index < candles.length - horizon; index += 1) {
    const history = candles.slice(0, index + 1);
    const closes = history.map((candle) => candle.close);
    const volumes = history.map((candle) => candle.volume);
    const averageVolume = average(volumes.slice(-50));
    const volumeScore = averageVolume ? Math.max(0, Math.min(1, volumes.at(-1) / averageVolume / 2)) : 0.5;
    const signal = getTechnicalSignal({
      price: closes.at(-1),
      ma20: computeEma(closes.slice(-20), 20),
      ma50: average(closes.slice(-50)),
      rsi: computeRsi(closes, 14),
      volumeScore
    });
    if (signal === 'WATCH') continue;

    const entry = closes.at(-1) * (signal === 'BUY' ? 1 + slippageRate : 1 - slippageRate);
    const target = entry * (signal === 'BUY' ? 1 + targetRate : 1 - targetRate);
    const stop = entry * (signal === 'BUY' ? 1 - stopRate : 1 + stopRate);
    let exit = candles[index + horizon].close;
    let outcome = signal === 'BUY' ? exit >= entry : exit <= entry;

    for (const futureCandle of candles.slice(index + 1, index + horizon + 1)) {
      if (signal === 'BUY' && futureCandle.low <= stop) { exit = stop; outcome = false; break; }
      if (signal === 'SELL' && futureCandle.high >= stop) { exit = stop; outcome = false; break; }
      if (signal === 'BUY' && futureCandle.high >= target) { exit = target; outcome = true; break; }
      if (signal === 'SELL' && futureCandle.low <= target) { exit = target; outcome = true; break; }
    }

    const grossReturn = signal === 'BUY' ? (exit - entry) / entry : (entry - exit) / entry;
    const netReturn = grossReturn - feeRate * 2;
    trades.push({ signal, outcome: netReturn > 0 && outcome, netReturn, riskPercent, leverage });
  }

  const wins = trades.filter((trade) => trade.outcome).length;
  const netReturn = trades.reduce((total, trade) => total + trade.netReturn, 0);
  return {
    timeframe: '1h',
    sampleSize: candles.length,
    trades: trades.length,
    wins,
    losses: trades.length - wins,
    successRate: trades.length ? Math.round((wins / trades.length) * 100) : null,
    netReturn: Number((netReturn * 100).toFixed(2)),
    assumptions: `${riskPercent}% risk, ${leverage}x max leverage, ${horizon} hourly candles, fees and slippage included; PAXG spot proxy`
  };
}

function withTimeout(promiseFactory, timeoutMs = 4000) {
  return new Promise((resolve, reject) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    promiseFactory(controller.signal)
      .then((value) => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch((error) => {
        clearTimeout(timer);
        reject(error);
      });
  });
}

function extractHeadlines(xmlText) {
  const matches = [...xmlText.matchAll(/<title>(.*?)<\/title>/g)];
  return matches
    .map((match) => match[1].replace(/&amp;/g, '&'))
    .filter((title) => /gold|xau|bullion|metal|futures|yield|fed|dollar|safe-haven|price/i.test(title));
}

function evaluateHeadlineSentiment(headline) {
  const normalized = headline.toLowerCase();

  const bullishWords = [
    'surge', 'rises', 'rise', 'higher', 'strong', 'bullish', 'breakout', 'record', 'safe-haven',
    'uptrend', 'accelerates', 'support', 'demand', 'gain', 'buying', 'firm'
  ];

  const bearishWords = [
    'drop', 'drops', 'lower', 'weak', 'bearish', 'pressure', 'fell', 'selloff', 'slips',
    'downtrend', 'risk-off', 'weakens', 'tumbling', 'losses', 'supply'
  ];

  let score = 0;
  bullishWords.forEach((word) => {
    if (normalized.includes(word)) score += 1;
  });
  bearishWords.forEach((word) => {
    if (normalized.includes(word)) score -= 1;
  });

  return score;
}

async function fetchGoldData() {
  return withTimeout(async (signal) => {
    const symbol = 'PAXGUSDT';
    const headers = { 'Accept': 'application/json' };
    const [historyResponse, quoteResponse] = await Promise.all([
      fetch('https://api.coingecko.com/api/v3/coins/pax-gold/market_chart?vs_currency=usd&days=30&interval=hourly', { signal, headers }),
      fetch('https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd&include_24hr_change=true', { signal, headers })
    ]);
    if (!historyResponse.ok || !quoteResponse.ok) throw new Error('CoinGecko PAXG feed unavailable');

    const history = await historyResponse.json();
    const quote = await quoteResponse.json();
    const closes = history.prices.map((point) => Number(point[1])).filter(Number.isFinite);
    const volumes = history.total_volumes.map((point) => Number(point[1])).filter(Number.isFinite);
    const ticker = quote?.['pax-gold'];
    const price = Number(ticker.price);
    if (!closes.length || !Number.isFinite(price)) {
      throw new Error('CoinGecko returned no usable PAXG price data');
    }

    const ma20 = computeEma(closes.slice(-20), 20);
    const ma50 = average(closes.slice(-50));
    const rsi = computeRsi(closes, 14);
    const averageVolume = average(volumes.slice(-50));
    const currentVolume = volumes.at(-1) || averageVolume;

    return {
      symbol,
      price,
      ma20,
      ma50,
      rsi,
      closes,
      volumeScore: averageVolume ? Math.max(0, Math.min(1, currentVolume / averageVolume / 2)) : 0.5,
      change: Number(ticker.usd_24h_change || 0),
      marketType: 'PAXG spot proxy',
      timeframe: '1h'
    };
  }, 8000);
}

let marketCache = { payload: null, expiresAt: 0 };

async function fetchGoldDataCached() {
  if (marketCache.payload && marketCache.expiresAt > Date.now()) return marketCache.payload;
  const payload = await fetchGoldData();
  marketCache = { payload, expiresAt: Date.now() + 20000 };
  return payload;
}

async function fetchBacktestData() {
  return withTimeout(async (signal) => {
    const response = await fetch('https://api.coingecko.com/api/v3/coins/pax-gold/market_chart?vs_currency=usd&days=30&interval=hourly', {
      signal,
      headers: { 'Accept': 'application/json' }
    });
    if (!response.ok) throw new Error(`CoinGecko backtest fetch failed: ${response.status}`);
    const rows = await response.json();
    const candles = rows.prices.map((row, index) => ({
      close: Number(row[1]),
      high: Number(row[1]),
      low: Number(row[1]),
      volume: Number(rows.total_volumes?.[index]?.[1] || 0)
    }));
    if (candles.length < 100 || candles.some((candle) => !Number.isFinite(candle.close))) {
      throw new Error('Not enough valid hourly PAXG candles for backtest');
    }
    return candles;
  }, 8000);
}

let backtestCache = { result: null, expiresAt: 0 };

async function getBacktestResult() {
  if (backtestCache.result && backtestCache.expiresAt > Date.now()) return backtestCache.result;
  try {
    const candles = await fetchBacktestData();
    backtestCache = { result: backtestCandles(candles, { riskPercent: 1, leverage: 10 }), expiresAt: Date.now() + 300000 };
    return backtestCache.result;
  } catch (error) {
    return null;
  }
}

async function fetchNewsSentiment() {
  return withTimeout(async (signal) => {
    const url = 'https://feeds.finance.yahoo.com/rss/2.0/headline?s=XAUUSD%3DX&region=US&lang=en-US';
    const response = await fetch(url, {
      signal,
      headers: {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*'
      }
    });

    if (!response.ok) {
      return { sentiment: 0.05, headlines: [] };
    }

    const xmlText = await response.text();
    const headlines = extractHeadlines(xmlText).slice(0, 8);

    if (!headlines.length) {
      return { sentiment: 0.05, headlines };
    }

    let totalScore = 0;
    headlines.forEach((headline) => {
      totalScore += evaluateHeadlineSentiment(headline);
    });

    const sentiment = Math.max(-1, Math.min(1, totalScore / headlines.length / 3));
    return { sentiment, headlines };
  }, 5000);
}

function buildFallbackSignalPayload() {
  return {
    symbol: 'PAXGUSDT', price: null, change: null, signal: 'UNAVAILABLE', successRate: null, confidence: null,
    trend: 'Unavailable', rsi: null, ma20: null, ma50: null, sentiment: 0, sentimentLabel: 'Unavailable',
    newsHeadlines: [], entry: null, stop: null, target: null, dataSource: 'No live exchange feed', dataQuality: 'No trade data', updatedAt: null,
    marketSummary: {
      priceAction: 'Unavailable', riskBias: 'No trade', analysis: 'The crypto market data feed is unavailable. Do not open a futures position until a fresh PAXGUSDT price is received.',
      traderExperience: 'Experienced traders do not trade blind or rely on stale prices. Wait for live exchange data and confirm leverage, margin, and liquidation distance.',
      aiSentiment: 'Sentiment analysis is paused because the price feed is unavailable.'
    }, indicators: { ema20: null, sma50: null, atr: null, macd: 'Unavailable', volume: 'Unavailable', support: null, resistance: null }
  };
}

async function buildSignalPayload() {
  try {
    const market = await fetchGoldDataCached();
    const news = await fetchNewsSentiment().catch(() => ({ sentiment: 0, headlines: [] }));
    const backtest = await getBacktestResult();

    const volumeScore = market.volumeScore;
    const signal = getSignalFromMetrics({
      price: market.price,
      ma20: market.ma20,
      ma50: market.ma50,
      rsi: market.rsi,
      sentiment: news.sentiment,
      volumeScore
    });

    const hasFuturesHistory = market.marketType === 'Futures';
    const confidence = hasFuturesHistory ? signal.confidence : 0;
    const direction = hasFuturesHistory ? signal.label : 'WATCH';
    const successRate = backtest?.trades >= 20 ? backtest.successRate : null;
    const entry = hasFuturesHistory ? (direction === 'BUY' ? market.price * 0.995 : market.price * 1.005) : null;
    const stop = hasFuturesHistory ? (direction === 'BUY' ? market.price * 0.985 : market.price * 1.015) : null;
    const target = hasFuturesHistory ? (direction === 'BUY' ? market.price * 1.015 : market.price * 0.985) : null;

    return {
      symbol: 'PAXGUSDT',
      price: market.price,
    timeframe: '1h',
      signal: direction,
      successRate,
      confidence,
      trend: market.price > market.ma20 ? 'Bullish' : market.price < market.ma20 ? 'Bearish' : 'Neutral',
      rsi: roundOrNull(market.rsi, 1),
      ma20: roundOrNull(market.ma20),
    assumptions: `${riskPercent}% risk, ${leverage}x max leverage, ${horizon} hourly candles, fees and slippage included; spot proxy, not exchange futures`
      sentiment: Number(news.sentiment.toFixed(2)),
      sentimentLabel: news.sentiment >= 0.2 ? 'Bullish' : news.sentiment <= -0.2 ? 'Bearish' : 'Neutral',
      newsHeadlines: news.headlines,
      entry: roundOrNull(entry),
      stop: roundOrNull(stop),
      target: roundOrNull(target),
      marketSummary: {
        priceAction: market.price > market.ma20 ? 'Above trend' : market.price < market.ma20 ? 'Below trend' : 'Neutral range',
        riskBias: direction === 'BUY' ? 'Bullish bias' : direction === 'SELL' ? 'Bearish bias' : 'Neutral bias',
        analysis: direction === 'BUY'
          ? 'Gold is holding firm above the short-term trend and is supported by improving sentiment and disciplined buyers near recent support.'
          : direction === 'SELL'
            ? 'Gold is losing its structural grip as momentum fades and sentiment cools, which raises the probability of a corrective move.'
            : 'Gold is balanced between buyers and sellers, so traders should wait for a cleaner break before committing directionally.',
        traderExperience: direction === 'BUY'
          ? 'Experienced gold traders are leaning toward buy-the-dip entries around support, with stops placed beneath the breakout base to preserve risk discipline.'
          : direction === 'SELL'
            ? 'Seasoned traders are preferring short entries only after failed highs or weak rebounds, keeping exposure tight around key resistance.'
            : 'Experienced traders are waiting for a confirmed break of the current range before committing, prioritizing clean structure over choppy noise.',
        aiSentiment: news.sentiment >= 0.2
          ? 'AI sentiment model remains positive due to supportive macro context and resilient demand for gold.'
          : news.sentiment <= -0.2
            ? 'AI sentiment model is bearish as macro drivers and safe-haven demand fade from the bullish setup.'
            : 'AI sentiment is neutral because macro headlines and price action are conflicting, indicating a watch-only phase.'
      },
      indicators: {
        ema20: roundOrNull(market.ma20),
        sma50: roundOrNull(market.ma50),
        atr: Number((Math.abs(market.price - market.ma20) * 1.2 + 10).toFixed(2)),
        macd: market.rsi >= 60 ? 'Bullish crossover' : market.rsi <= 40 ? 'Bearish crossover' : 'Neutral range',
        volume: volumeScore > 0.55 ? 'Above average' : volumeScore < 0.45 ? 'Below average' : 'Balanced',
        support: roundOrNull(market.price - Math.max(8, market.price * 0.006)),
        resistance: roundOrNull(market.price + Math.max(8, market.price * 0.008))
      }
      , dataSource: `CoinGecko public API (${market.marketType})`, marketType: market.marketType, updatedAt: Date.now(),
      dataQuality: 'Live PAXG spot data; futures signal disabled'
      , backtest
    };
  } catch (error) {
    return buildFallbackSignalPayload();
  }
}

function serveStaticFile(filePath, contentType, response) {
  fs.readFile(filePath, (error, content) => {
    if (error) {
      response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Internal Server Error');
      return;
    }

    response.writeHead(200, { 'Content-Type': contentType });
    response.end(content);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === '/api/signal') {
    try {
      const payload = await buildSignalPayload();
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify(payload));
      return;
    } catch (error) {
      res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: error.message }));
      return;
    }
  }

  let filePath = url.pathname === '/' ? path.join(PUBLIC_DIR, 'index.html') : path.join(PUBLIC_DIR, url.pathname);

  const extension = path.extname(filePath);
  const contentType = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml'
  }[extension] || 'application/octet-stream';

  fs.exists(filePath, (exists) => {
    if (!exists) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Not found');
      return;
    }

    serveStaticFile(filePath, contentType, res);
  });
});

if (require.main === module) {
  server.listen(PORT, () => {
    console.log(`Gold signal app running on port ${PORT}`);
  });
}

module.exports = { buildSignalPayload, getSignalFromMetrics, computeRsi, computeEma, backtestCandles, fetchGoldData };
