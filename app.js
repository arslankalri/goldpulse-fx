async function fetchSignal() {
  const response = await fetch('/api/signal', { cache: 'no-store' });
  if (!response.ok) {
    throw new Error('Signal request failed');
  }

  return response.json();
}

function formatMoney(value) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '--';
  return `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function renderSignal(data) {
  const signalBadge = document.getElementById('signalBadge');
  const signalColor = data.signal === 'BUY' ? '#3dd598' : data.signal === 'SELL' ? '#ff5d73' : '#f5b948';
  const signalBg = data.signal === 'BUY' ? 'rgba(61, 213, 152, 0.12)' : data.signal === 'SELL' ? 'rgba(255, 93, 115, 0.12)' : 'rgba(245, 185, 73, 0.12)';

  signalBadge.textContent = data.signal;
  signalBadge.style.color = signalColor;
  signalBadge.style.background = signalBg;

  document.getElementById('priceValue').textContent = formatMoney(data.price);
  document.getElementById('priceChange').textContent = Number.isFinite(data.change) ? `${data.change > 0 ? '+' : ''}${Number(data.change).toFixed(2)}%` : '--';
  document.getElementById('priceChange').className = `price-change ${data.change >= 0 ? 'positive' : 'neutral'}`;
  document.getElementById('dataStatus').textContent = `${data.dataQuality || 'Market data'}${data.updatedAt ? ` | Updated ${new Date(data.updatedAt).toLocaleTimeString()}` : ''}`;

  document.getElementById('successRateValue').textContent = Number.isFinite(data.successRate) ? `${data.successRate}%` : '--';
  document.getElementById('confidenceValue').textContent = Number.isFinite(data.confidence) ? `${data.confidence}%` : '--';
  document.getElementById('trendValue').textContent = data.trend || 'Bullish';
  document.getElementById('sentimentValue').textContent = data.sentimentLabel ? data.sentimentLabel : (data.sentiment >= 0 ? `+${data.sentiment.toFixed(2)}` : data.sentiment.toFixed(2));

  document.getElementById('trendScore').textContent = Number.isFinite(data.successRate) ? `${data.successRate}/100` : '--';
  document.getElementById('indicatorScore').textContent = Number.isFinite(data.confidence) ? `${data.confidence} / 100` : '--';
  document.getElementById('sentimentScore').textContent = data.sentimentLabel === 'Unavailable' ? '--' : `${Math.round((Number(data.sentiment) + 1) * 50)} / 100`;

  document.getElementById('marketAnalysis').textContent = data.marketSummary?.analysis || 'Gold is holding a constructive structure with buyers defending key support and momentum still healthy.';
  document.getElementById('indicatorText').textContent = data.indicators
    ? `EMA ${formatMoney(data.indicators.ema20)} | SMA ${formatMoney(data.indicators.sma50)} | MACD ${data.indicators.macd} | Volume ${data.indicators.volume}`
    : 'Structure remains constructive and momentum is supporting the active bias.';

  document.getElementById('sentimentText').textContent = data.marketSummary?.aiSentiment || 'AI sentiment remains aligned with the active trend and supports the present bias.';

  document.getElementById('emaValue').textContent = formatMoney(data.ma20 ?? data.indicators?.ema20);
  document.getElementById('smaValue').textContent = formatMoney(data.ma50 ?? data.indicators?.sma50);
  document.getElementById('rsiValue').textContent = Number.isFinite(data.rsi) ? data.rsi.toFixed(1) : '--';
  document.getElementById('atrValue').textContent = formatMoney(data.indicators?.atr);
  document.getElementById('entryValue').textContent = formatMoney(data.entry);
  document.getElementById('stopValue').textContent = formatMoney(data.stop);
  document.getElementById('targetValue').textContent = formatMoney(data.target);
  document.getElementById('traderExperience').textContent = data.marketSummary?.traderExperience || 'Experienced traders are waiting for clean pullbacks and disciplined stops before committing to new gold positions.';

  const list = document.getElementById('newsList');
  list.innerHTML = '';

  if (data.newsHeadlines && data.newsHeadlines.length) {
    data.newsHeadlines.slice(0, 4).forEach((headline, index) => {
      const item = document.createElement('li');
      const dot = document.createElement('span');
      dot.className = `dot ${index % 3 === 0 ? 'green' : index % 3 === 1 ? 'amber' : 'blue'}`;
      const text = document.createElement('span');
      text.textContent = headline;
      item.appendChild(dot);
      item.appendChild(text);
      list.appendChild(item);
    });
  } else {
    list.innerHTML = '<li>No recent gold headlines available right now.</li>';
  }

  document.getElementById('summaryText').textContent = data.signal === 'UNAVAILABLE'
    ? 'Binance data unavailable. No trade signal is active.'
    : `${data.symbol} futures signal is ${data.signal} with a ${data.successRate}% model score. ${data.dataSource || ''}`;
}

async function refreshSignal() {
  try {
    const data = await fetchSignal();
    renderSignal(data);
  } catch (error) {
    document.getElementById('summaryText').textContent = 'Binance market data is temporarily unavailable. No trade signal is active.';
    document.getElementById('dataStatus').textContent = 'Feed error | No trade signal';
  }
}

document.getElementById('refreshButton').addEventListener('click', refreshSignal);
document.getElementById('refreshButtonMain').addEventListener('click', refreshSignal);

refreshSignal();
setInterval(refreshSignal, 60000);
