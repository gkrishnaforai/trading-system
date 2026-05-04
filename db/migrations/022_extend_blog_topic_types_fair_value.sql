-- Extend blog topic types to support fair value analysis blogs

ALTER TABLE blog_topics
    DROP CONSTRAINT IF EXISTS blog_topics_topic_type_check;

ALTER TABLE blog_topics
    ADD CONSTRAINT blog_topics_topic_type_check
    CHECK (topic_type IN (
        'signal_change',
        'golden_cross',
        'rsi_extreme',
        'earnings_proximity',
        'portfolio_heavy',
        'volume_spike',
        'trend_reversal',
        'fair_value_analysis'
    ));
