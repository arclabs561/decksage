/**
 * Evaluation Rubrics
 * 
 * Provides explicit scoring rubrics for LLM-as-a-judge evaluation.
 * Research shows that explicit rubrics improve reliability by 10-20%
 * and reduce bias from superficial features (LLMs-as-Judges Survey, arXiv:2412.05579).
 */

/**
 * Default scoring rubric for screenshot validation
 */
export const DEFAULT_RUBRIC = {
  score: {
    description: 'Overall quality score from 0-10',
    criteria: {
      10: 'Perfect - No issues, excellent UX, all requirements met',
      9: 'Excellent - Minor cosmetic issues, excellent UX',
      8: 'Very Good - Minor issues that don\'t affect usability',
      7: 'Good - Some issues but generally usable',
      6: 'Acceptable - Issues present but functional',
      5: 'Needs Improvement - Significant issues affecting usability',
      4: 'Poor - Major issues, difficult to use',
      3: 'Very Poor - Critical issues, barely functional',
      2: 'Bad - Severe issues, mostly broken',
      1: 'Very Bad - Almost completely broken',
      0: 'Broken - Completely non-functional'
    }
  },
  dimensions: {
    visual: {
      description: 'Visual design and aesthetics',
      criteria: [
        'Layout is clear and organized',
        'Colors are appropriate and accessible',
        'Typography is readable',
        'Spacing is consistent',
        'Visual hierarchy is clear'
      ]
    },
    functional: {
      description: 'Functional correctness',
      criteria: [
        'All interactive elements work correctly',
        'Forms submit properly',
        'Links navigate correctly',
        'Buttons trigger expected actions',
        'No broken functionality'
      ]
    },
    usability: {
      description: 'Ease of use',
      criteria: [
        'Purpose is clear',
        'Actions are obvious',
        'Feedback is provided',
        'Error messages are helpful',
        'Flow is intuitive'
      ]
    },
    accessibility: {
      description: 'Accessibility compliance',
      criteria: [
        'Keyboard navigation works',
        'Screen reader compatible',
        'Color contrast is sufficient',
        'Text is readable',
        'Interactive elements are accessible'
      ]
    }
  }
};

/**
 * Build rubric prompt section
 * 
 * @param {import('./index.mjs').Rubric | null} [rubric=null] - Rubric to use, or null for default
 * @param {boolean} [includeDimensions=true] - Whether to include evaluation dimensions
 * @returns {string} Formatted rubric prompt text
 */
export function buildRubricPrompt(rubric = null, includeDimensions = true) {
  const rubricToUse = rubric || DEFAULT_RUBRIC;
  let prompt = `## EVALUATION RUBRIC

### Scoring Scale (0-10):
${Object.entries(rubricToUse.score.criteria)
  .sort((a, b) => parseInt(b[0]) - parseInt(a[0]))
  .map(([score, desc]) => `- ${score}: ${desc}`)
  .join('\n')}

### Example Evaluations (Few-Shot Learning):

**Example 1 - High Quality (Score: 9)**
Screenshot: Clean, accessible homepage with high contrast
Evaluation: "Excellent design with clear navigation, high contrast (21:1), keyboard accessible. Minor: could improve spacing. Score: 9"
JSON: {"score": 9, "assessment": "excellent", "issues": ["minor spacing"], "reasoning": "High quality with minor improvements needed"}

**Example 2 - Medium Quality (Score: 6)**
Screenshot: Functional but cluttered interface
Evaluation: "Functional design but cluttered layout, moderate contrast (4.2:1), some accessibility issues. Score: 6"
JSON: {"score": 6, "assessment": "needs-improvement", "issues": ["cluttered layout", "low contrast", "accessibility issues"], "reasoning": "Functional but needs significant improvements"}

**Example 3 - Low Quality (Score: 3)**
Screenshot: Broken layout with poor accessibility
Evaluation: "Poor design with broken layout, very low contrast (2.1:1), not keyboard accessible, multiple critical issues. Score: 3"
JSON: {"score": 3, "assessment": "fail", "issues": ["broken layout", "critical contrast violation", "no keyboard navigation"], "reasoning": "Multiple critical issues prevent usability"}

### Evaluation Instructions:
1. Evaluate the screenshot against the criteria below
2. Consider both appearance and functional correctness
3. Base your score on substantive content, not superficial features
4. Ignore factors like response length, verbosity, or formatting style
5. Focus on actual quality: correctness, clarity, usability, and accessibility
6. Provide a score from 0-10 based on the rubric above
7. List specific issues found (if any)
8. Provide reasoning for your score`;

  if (includeDimensions && rubricToUse.dimensions) {
    prompt += `\n\n### Evaluation Dimensions:
${Object.entries(rubricToUse.dimensions)
  .map(([key, dim]) => `\n**${key.toUpperCase()}** (${dim.description}):\n${dim.criteria.map(c => `- ${c}`).join('\n')}`)
  .join('\n')}`;
  }

  prompt += `\n\n### Issue Importance and Annoyance:
For each issue you identify, consider:
- **Importance**: How critical is this issue? (critical, high, medium, low)
- **Annoyance**: How annoying/frustrating is this issue to users? (very-high, high, medium, low)
- **Impact**: What is the impact on user experience? (blocks-use, degrades-experience, minor-inconvenience, cosmetic)

### Suggestions and Evidence:
When providing recommendations, include:
- **Specific suggestions**: Concrete, actionable improvements
- **Evidence**: What in the screenshot supports your judgment? (visual elements, layout issues, accessibility violations, etc.)
- **Priority**: Which issues should be fixed first? (based on importance and annoyance)

### Output Format:
Provide your evaluation as JSON:
{
  "score": <0-10 integer>,
  "assessment": "<pass|fail|needs-improvement>",
  "issues": [
    {
      "description": "<issue description>",
      "importance": "<critical|high|medium|low>",
      "annoyance": "<very-high|high|medium|low>",
      "impact": "<blocks-use|degrades-experience|minor-inconvenience|cosmetic>",
      "evidence": "<what in the screenshot supports this issue>",
      "suggestion": "<specific, actionable recommendation>"
    }
  ],
  "reasoning": "<explanation of score>",
  "strengths": ["<strength1>", "<strength2>", ...],
  "recommendations": [
    {
      "priority": "<high|medium|low>",
      "suggestion": "<specific recommendation>",
      "evidence": "<what supports this recommendation>",
      "expectedImpact": "<what improvement this would bring>"
    }
  ],
  "evidence": {
    "visual": "<visual evidence from screenshot>",
    "functional": "<functional evidence>",
    "accessibility": "<accessibility evidence>"
  }
}`;

  return prompt;
}

/**
 * Get rubric for specific test type
 * 
 * @param {string} testType - Test type identifier (e.g., 'payment-screen', 'gameplay', 'form')
 * @returns {import('./index.mjs').Rubric} Rubric configured for the test type
 */
export function getRubricForTestType(testType) {
  const testTypeRubrics = {
    'payment-screen': {
      ...DEFAULT_RUBRIC,
      dimensions: {
        ...DEFAULT_RUBRIC.dimensions,
        payment: {
          description: 'Payment functionality',
          criteria: [
            'Payment code is clearly visible',
            'Payment links are obvious',
            'Payment flow is trustworthy',
            'Connection to game access is clear',
            'Payment instructions are clear'
          ]
        }
      }
    },
    'gameplay': {
      ...DEFAULT_RUBRIC,
      dimensions: {
        ...DEFAULT_RUBRIC.dimensions,
        gameplay: {
          description: 'Gameplay experience',
          criteria: [
            'Game is visually engaging',
            'Controls are intuitive',
            'Feedback is clear',
            'Game is balanced',
            'Experience is fun'
          ]
        }
      }
    },
    'form': {
      ...DEFAULT_RUBRIC,
      dimensions: {
        ...DEFAULT_RUBRIC.dimensions,
        form: {
          description: 'Form usability',
          criteria: [
            'Labels are clear',
            'Placeholders are helpful',
            'Validation is clear',
            'Submit button is obvious',
            'Error messages are helpful'
          ]
        }
      }
    }
  };

  return testTypeRubrics[testType] || DEFAULT_RUBRIC;
}

