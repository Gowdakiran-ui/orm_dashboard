export interface SentimentDistribution {
  positive: number;
  neutral: number;
  negative: number;
}

export function calculateSentimentDistribution(documents: any[]): SentimentDistribution {
  let positive = 0;
  let neutral = 0;
  let negative = 0;

  (documents || []).forEach(d => {
    if (d && d.sentiment !== undefined && d.sentiment !== null) {
      if (d.sentiment > 0.3) positive++;
      else if (d.sentiment < -0.3) negative++;
      else neutral++;
    }
  });

  return { positive, neutral, negative };
}
