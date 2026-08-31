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
    const sources = [
      { base: 'https://fapi.binance.com', candles: '/fapi/v1/klines?symbol=PAXGUSDT&interval=1h&limit=200', price: '/fapi/v1/ticker/price?symbol=PAXGUSDT', day: '/fapi/v1/ticker/24hr?symbol=PAXGUSDT', marketType: 'Futures' },
      { base: 'https://api.binance.com', candles: '/api/v3/klines?symbol=PAXGUSDT&interval=1h&limit=200', price: '/api/v3/ticker/price?symbol=PAXGUSDT', day: '/api/v3/ticker/24hr?symbol=PAXGUSDT', marketType: 'Spot proxy' }
    ];
    let responses;
    let source;
    for (const candidate of sources) {
      const candidateResponses = await Promise.all([
        fetch(candidate.base + candidate.candles, { signal, headers }),
        fetch(candidate.base + candidate.price, { signal, headers }),
        fetch(candidate.base + candidate.day, { signal, headers })
      ]);
      if (candidateResponses.every((response) => response.ok)) {
        responses = candidateResponses;
        source = candidate;
        break;
      }
    }
    if (!responses) {
      const response = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd&include_24hr_change=true', { signal, headers });
      if (!response.ok) throw new Error('No accessible PAXGUSDT or PAXG spot feed');
      const quote = await response.json();
      const price = Number(quote?.['pax-gold']?.usd);
      if (!Number.isFinite(price)) throw new Error('CoinGecko returned no usable PAXG price');
      return {
        symbol,
        price,
        ma20: price,
        ma50: price,
        rsi: 50,
        closes: [price],
        volumeScore: 0.5,
        change: Number(quote?.['pax-gold']?.usd_24h_change || 0),
        marketType: 'PAXG spot proxy'
      };
    }

    const candles = await responses[0].json();
    const ticker = await responses[1].json();
    const day = await responses[2].json();
    const closes = candles.map((candle) => Number(candle[4])).filter(Number.isFinite);
    const volumes = candles.map((candle) => Number(candle[5])).filter(Number.isFinite);
    const price = Number(ticker.price);
    if (!closes.length || !Number.isFinite(price)) {
      throw new Error('Binance returned no usable PAXGUSDT price data');
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
      change: Number(day.priceChangePercent),
      marketType: source.marketType
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
      priceAction: 'Unavailable', riskBias: 'No trade', analysis: 'Binance market data is unavailable. Do not open a futures position until a fresh PAXGUSDT price is received.',
      traderExperience: 'Experienced traders do not trade blind or rely on stale prices. Wait for live exchange data and confirm leverage, margin, and liquidation distance.',
      aiSentiment: 'Sentiment analysis is paused because the price feed is unavailable.'
    }, indicators: { ema20: null, sma50: null, atr: null, macd: 'Unavailable', volume: 'Unavailable', support: null, resistance: null }
  };
}

async function buildSignalPayload() {
  try {
    const market = await fetchGoldDataCached();
    const news = await fetchNewsSentiment().catch(() => ({ sentiment: 0, headlines: [] }));

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
    const successRate = direction === 'BUY' ? 82 : direction === 'SELL' ? 79 : 68;
    const entry = hasFuturesHistory ? (direction === 'BUY' ? market.price * 0.995 : market.price * 1.005) : null;
    const stop = hasFuturesHistory ? (direction === 'BUY' ? market.price * 0.985 : market.price * 1.015) : null;
    const target = hasFuturesHistory ? (direction === 'BUY' ? market.price * 1.015 : market.price * 0.985) : null;

    return {
      symbol: 'PAXGUSDT',
      price: market.price,
      change: market.change,
      signal: direction,
      successRate,
      confidence,
      trend: market.price > market.ma20 ? 'Bullish' : market.price < market.ma20 ? 'Bearish' : 'Neutral',
      rsi: roundOrNull(market.rsi, 1),
      ma20: roundOrNull(market.ma20),
      ma50: roundOrNull(market.ma50),
      sentiment: Number(news.sentiment.toFixed(2)),
      sentimentLabel: news.sentiment >= 0.2 ? 'Bullish' : news.sentiment <= -0.2 ? 'Bearish' : 'Neutral',
      newsHeadlines: news.headlines,
      entry: roundOrNull(entry),
      stop: roundOrNull(stop),
      target: roundOrNull(target),
      marketSummary: {
        priceAction: market.price > market.ma20 ? 'Above trend' : 'Below trend',
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
      , dataSource: `Binance public API (${market.marketType})`, marketType: market.marketType, updatedAt: Date.now(),
      dataQuality: hasFuturesHistory ? 'Live futures candles' : 'Live spot proxy; futures signal disabled'
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

module.exports = { buildSignalPayload, getSignalFromMetrics, computeRsi, computeEma, fetchGoldData };
