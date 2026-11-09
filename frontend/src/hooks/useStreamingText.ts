'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

interface UseStreamingTextOptions {
  text: string;
  speed?: number; // ms per character
  enabled?: boolean;
  onComplete?: () => void;
}

export function useStreamingText({
  text,
  speed = 15,
  enabled = true,
  onComplete,
}: UseStreamingTextOptions) {
  const [displayedText, setDisplayedText] = useState('');
  const [isComplete, setIsComplete] = useState(false);
  const indexRef = useRef(0);
  const onCompleteRef = useRef(onComplete);

  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (!enabled || !text) {
      setDisplayedText(text || '');
      setIsComplete(true);
      return;
    }

    indexRef.current = 0;
    setDisplayedText('');
    setIsComplete(false);

    const interval = setInterval(() => {
      indexRef.current += 1;

      // Stream in chunks of 1-3 characters for natural feel
      const chunkSize = Math.random() < 0.3 ? 2 : 1;
      const nextIndex = Math.min(indexRef.current + chunkSize - 1, text.length);
      indexRef.current = nextIndex;

      setDisplayedText(text.slice(0, nextIndex));

      if (nextIndex >= text.length) {
        clearInterval(interval);
        setIsComplete(true);
        onCompleteRef.current?.();
      }
    }, speed);

    return () => clearInterval(interval);
  }, [text, speed, enabled]);

  const skipToEnd = useCallback(() => {
    setDisplayedText(text);
    setIsComplete(true);
    onCompleteRef.current?.();
  }, [text]);

  return { displayedText, isComplete, skipToEnd };
}
