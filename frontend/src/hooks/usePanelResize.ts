'use client';

import { useState, useCallback, useEffect, useRef } from 'react';

interface UsePanelResizeOptions {
  direction: 'horizontal' | 'vertical';
  initialSize: number; // percentage or pixels
  minSize?: number;
  maxSize?: number;
  containerRef: React.RefObject<HTMLElement | null>;
  onResize?: (size: number) => void;
}

export function usePanelResize({
  direction,
  initialSize,
  minSize = 20,
  maxSize = 80,
  containerRef,
  onResize,
}: UsePanelResizeOptions) {
  const [size, setSize] = useState(initialSize);
  const isDragging = useRef(false);
  const startPos = useRef(0);
  const startSize = useRef(initialSize);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      isDragging.current = true;
      startPos.current = direction === 'horizontal' ? e.clientX : e.clientY;
      startSize.current = size;
      document.body.style.cursor = direction === 'horizontal' ? 'col-resize' : 'row-resize';
      document.body.style.userSelect = 'none';
    },
    [direction, size]
  );

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;

      const container = containerRef.current;
      const rect = container.getBoundingClientRect();
      const totalSize = direction === 'horizontal' ? rect.width : rect.height;
      const currentPos = direction === 'horizontal' ? e.clientX : e.clientY;
      const containerStart = direction === 'horizontal' ? rect.left : rect.top;

      const newSizePercent = ((currentPos - containerStart) / totalSize) * 100;
      const clampedSize = Math.max(minSize, Math.min(maxSize, newSizePercent));

      setSize(clampedSize);
      onResize?.(clampedSize);
    };

    const handleMouseUp = () => {
      isDragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [direction, minSize, maxSize, containerRef, onResize]);

  const resetSize = useCallback(() => {
    setSize(initialSize);
    onResize?.(initialSize);
  }, [initialSize, onResize]);

  return { size, handleMouseDown, resetSize, isDragging: isDragging.current };
}
