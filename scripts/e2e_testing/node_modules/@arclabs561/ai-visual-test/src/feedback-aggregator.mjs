/**
 * Feedback Aggregator
 * 
 * Aggregates judge feedback across multiple tests for iterative improvement.
 * 
 * General-purpose utility - no domain-specific logic.
 */

/**
 * Aggregate judge feedback from multiple test runs
 * 
 * @param {import('./index.mjs').ValidationResult[]} judgeResults - Array of validation results
 * @returns {import('./index.mjs').AggregatedFeedback} Aggregated feedback with statistics and recommendations
 */
export function aggregateFeedback(judgeResults) {
  const aggregated = {
    scores: [],
    issues: {},
    recommendations: {},
    strengths: {},
    weaknesses: {},
    actionableItems: {},
    categories: {
      visual: [],
      functional: [],
      performance: [],
      accessibility: [],
      gameplay: [],
      ux: [],
      other: []
    },
    priority: {
      critical: [],
      high: [],
      medium: [],
      low: []
    },
    trends: {
      score: [],
      issues: [],
      recommendations: []
    }
  };

  judgeResults.forEach(result => {
    // Aggregate scores
    if (result.score !== null && result.score !== undefined) {
      aggregated.scores.push(result.score);
    }

    // Aggregate semantic information
    if (result.semantic) {
      const sem = result.semantic;

      // Aggregate issues by frequency
      if (sem.issues) {
        sem.issues.forEach(issue => {
          aggregated.issues[issue] = (aggregated.issues[issue] || 0) + 1;
        });
      }

      // Aggregate recommendations
      if (sem.recommendations) {
        sem.recommendations.forEach(rec => {
          aggregated.recommendations[rec] = (aggregated.recommendations[rec] || 0) + 1;
        });
      }

      // Aggregate strengths
      if (sem.strengths) {
        sem.strengths.forEach(strength => {
          aggregated.strengths[strength] = (aggregated.strengths[strength] || 0) + 1;
        });
      }

      // Aggregate weaknesses
      if (sem.weaknesses) {
        sem.weaknesses.forEach(weakness => {
          aggregated.weaknesses[weakness] = (aggregated.weaknesses[weakness] || 0) + 1;
        });
      }

      // Aggregate actionable items
      if (sem.actionableItems) {
        sem.actionableItems.forEach(item => {
          aggregated.actionableItems[item] = (aggregated.actionableItems[item] || 0) + 1;
        });
      }

      // Aggregate by category
      if (sem.semanticCategories) {
        Object.entries(sem.semanticCategories).forEach(([category, items]) => {
          if (items && items.length > 0) {
            aggregated.categories[category] = aggregated.categories[category] || [];
            aggregated.categories[category].push(...items);
          }
        });
      }

      // Aggregate by priority
      if (sem.priority) {
        Object.entries(sem.priority).forEach(([level, items]) => {
          if (items && items.length > 0) {
            aggregated.priority[level] = aggregated.priority[level] || [];
            aggregated.priority[level].push(...items);
          }
        });
      }
    }
  });

  // Calculate statistics
  const stats = {
    totalJudgments: judgeResults.length,
    averageScore: aggregated.scores.length > 0 
      ? aggregated.scores.reduce((a, b) => a + b, 0) / aggregated.scores.length 
      : null,
    minScore: aggregated.scores.length > 0 ? Math.min(...aggregated.scores) : null,
    maxScore: aggregated.scores.length > 0 ? Math.max(...aggregated.scores) : null,
    mostCommonIssues: Object.entries(aggregated.issues)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([issue, count]) => ({ issue, count })),
    mostCommonRecommendations: Object.entries(aggregated.recommendations)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([rec, count]) => ({ rec, count })),
    mostCommonStrengths: Object.entries(aggregated.strengths)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([strength, count]) => ({ strength, count })),
    mostCommonWeaknesses: Object.entries(aggregated.weaknesses)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([weakness, count]) => ({ weakness, count })),
    mostCommonActionableItems: Object.entries(aggregated.actionableItems)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([item, count]) => ({ item, count })),
    categoryCounts: Object.entries(aggregated.categories)
      .map(([category, items]) => ({ category, count: items.length }))
      .sort((a, b) => b.count - a.count),
    priorityCounts: Object.entries(aggregated.priority)
      .map(([level, items]) => ({ level, count: items.length }))
      .sort((a, b) => {
        const order = { critical: 0, high: 1, medium: 2, low: 3 };
        return (order[a.level] || 99) - (order[b.level] || 99);
      })
  };

  return {
    aggregated,
    stats,
    summary: generateSummary(aggregated, stats)
  };
}

/**
 * Generate human-readable summary
 */
function generateSummary(aggregated, stats) {
  const parts = [];

  parts.push(`Aggregated ${stats.totalJudgments} judge results.`);

  if (stats.averageScore !== null) {
    parts.push(`Average score: ${stats.averageScore.toFixed(1)}/10 (range: ${stats.minScore}-${stats.maxScore}).`);
  }

  if (stats.mostCommonIssues.length > 0) {
    parts.push(`Most common issues: ${stats.mostCommonIssues.slice(0, 3).map(i => i.issue).join(', ')}.`);
  }

  if (stats.mostCommonRecommendations.length > 0) {
    parts.push(`Most common recommendations: ${stats.mostCommonRecommendations.slice(0, 3).map(r => r.rec).join(', ')}.`);
  }

  if (stats.priorityCounts.length > 0) {
    const critical = stats.priorityCounts.find(p => p.level === 'critical');
    if (critical && critical.count > 0) {
      parts.push(`Critical issues: ${critical.count}.`);
    }
  }

  return parts.join(' ');
}

/**
 * Generate recommendations from aggregated feedback
 * 
 * @param {import('./index.mjs').AggregatedFeedback} aggregated - Aggregated feedback
 * @returns {string[]} Array of recommendation strings
 */
export function generateRecommendations(aggregated) {
  const recommendations = [];

  // Critical priority items
  if (aggregated.priority.critical && aggregated.priority.critical.length > 0) {
    recommendations.push({
      priority: 'critical',
      category: 'all',
      items: aggregated.priority.critical.slice(0, 5),
      description: 'Critical issues that must be addressed immediately'
    });
  }

  // High priority items
  if (aggregated.priority.high && aggregated.priority.high.length > 0) {
    recommendations.push({
      priority: 'high',
      category: 'all',
      items: aggregated.priority.high.slice(0, 5),
      description: 'High priority issues that should be addressed soon'
    });
  }

  // Category-specific recommendations
  Object.entries(aggregated.categories).forEach(([category, items]) => {
    if (items && items.length > 0) {
      const uniqueItems = [...new Set(items)];
      if (uniqueItems.length > 0) {
        recommendations.push({
          priority: 'medium',
          category,
          items: uniqueItems.slice(0, 5),
          description: `${category} improvements`
        });
      }
    }
  });

  // Most common actionable items
  const actionableEntries = Object.entries(aggregated.actionableItems || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  
  if (actionableEntries.length > 0) {
    recommendations.push({
      priority: 'medium',
      category: 'actionable',
      items: actionableEntries.map(([item, count]) => `${item} (mentioned ${count} times)`),
      description: 'Most frequently mentioned actionable improvements'
    });
  }

  return recommendations;
}

