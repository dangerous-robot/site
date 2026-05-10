---
title: Should I Use AI for This?
description: A reflective tool to help you think through whether AI is the right fit for your task. Not a quiz, just questions worth asking.
pubDate: 2026-03-04
layout: tool
wallpaper: default
topics:
  - ai-literacy
data:
  intro:
    eyebrow: Quick tool to help decide when to use AI
    headline: Every AI prompt carries trade-offs.
    body: Environmental cost. Accuracy risk. Cognitive outsourcing. This tool helps you weigh them for a specific task.
    prompt_headline: Think of something specific.
    prompt_body: A prompt you're about to type. A project. A workflow. Six questions will help you think it through.
    cta: I have something in mind
  lens_step:
    headline: How do you generally feel about AI?
    options:
      - id: cautious
        label: I'm wary of it
        description: I worry about what AI means for jobs, truth, and human connection.
      - id: skeptical
        label: I use it sometimes
        description: I see the value, but I'm not sure I trust it.
      - id: enthusiastic
        label: I'm all in
        description: I use AI regularly and want to use it well.
    skip_label: "Skip this step →"
  questions:
    - id: qc-task-type
      text: What kind of task is this?
      answers:
        - id: ct-create
          text: Creating something new
          score: { growth: -15 }
        - id: ct-analyze
          text: Analyzing or summarizing
          score: { alternatives: 10, growth: 10 }
        - id: ct-automate
          text: Automating repetitive work
          score: { alternatives: 15, growth: 15 }
        - id: ct-learn
          text: Learning or understanding
          score: { growth: -20 }
    - id: qc-stakes
      text: What happens if the output is wrong?
      answers:
        - id: cs-nothing
          text: Nothing significant
          score: { risk: 10 }
        - id: cs-waste
          text: Wasted time or effort
          score: { risk: -10 }
        - id: cs-real
          text: Real harm or serious consequences
          score: { risk: -25 }
    - id: qc-personal
      text: How personal is this work?
      answers:
        - id: cp-functional
          text: Purely functional, doesn't represent me
          score: { growth: 10 }
        - id: cp-mixed
          text: Somewhat personal, I'll make it mine
          score: { growth: -10 }
        - id: cp-deeply
          text: Deeply personal, my voice matters
          score: { growth: -20 }
    - id: qc-alternatives
      text: Are there good non-AI alternatives?
      answers:
        - id: calt-no
          text: Not really, AI is the best option
          score: { alternatives: 15 }
        - id: calt-some
          text: Some, but AI has a real edge here
          score: { alternatives: -5 }
        - id: calt-yes
          text: Yes, simpler tools would work fine
          score: { alternatives: -20 }
    - id: qc-scale
      text: How much AI firepower does this need?
      context: A quick text query uses roughly 0.03g CO2. Multi-turn sessions with large contexts and image generation can use 50 to 100 times that.
      answers:
        - id: csc-light
          text: Light, quick question, short answer
          score: { alternatives: 5 }
        - id: csc-moderate
          text: Moderate, a few paragraphs or some analysis
          score: {}
        - id: csc-heavy
          text: Heavy, big context, multiple rounds, maybe images
          score: { risk: 5 }
    - id: qc-intentionality
      text: Is this intentional or habitual?
      answers:
        - id: ci-intentional
          text: I've thought about it, this is the right call
          score: { growth: 5 }
        - id: ci-unsure
          text: I'm not sure
          score: { growth: -5 }
        - id: ci-habit
          text: Probably habit
          score: { growth: -15 }
  dimensions:
    - key: risk
      lowLabel: High stakes, verify everything
      highLabel: Low stakes, safe to experiment
    - key: growth
      lowLabel: Do it yourself, you'd learn more
      highLabel: Routine task, AI saves time
    - key: alternatives
      lowLabel: Simpler tools work fine
      highLabel: AI is the right tool
  closers:
    cautious: Your caution is an asset. Use it to guide how, and whether, you engage.
    skeptical: The fact that you're thinking about this puts you ahead of most AI users.
    enthusiastic: Being intentional about AI usage is what separates effective use from habitual use.
---

## About this tool

Six questions, no verdicts. This tool helps you think through the trade-offs of using AI for a specific task. The "answers" are considerations, not scores; you know your situation better than we do.

When we say "AI" here, we mean generative AI: tools like ChatGPT, Claude, and Gemini that produce text, images, or code. Machine learning in controlled settings (medical imaging, weather prediction, structural engineering) is a different discussion with different trade-offs.
