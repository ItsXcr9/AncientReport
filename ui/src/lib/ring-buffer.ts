/**
 * Ring Buffer for efficient metric storage
 * 
 * Fixed-size circular buffer that automatically overwrites oldest data
 * when capacity is reached. O(1) insertions and reads.
 */

export interface DataPoint {
  timestamp: string;
  value: number;
  [key: string]: any;
}

export class RingBuffer<T extends DataPoint> {
  private buffer: T[];
  private capacity: number;
  private head: number = 0; // Write position
  private size: number = 0; // Current size
  
  constructor(capacity: number) {
    this.capacity = capacity;
    this.buffer = new Array(capacity);
  }
  
  /**
   * Add a data point to the buffer
   */
  public push(item: T): void {
    this.buffer[this.head] = item;
    this.head = (this.head + 1) % this.capacity;
    
    if (this.size < this.capacity) {
      this.size++;
    }
  }
  
  /**
   * Add multiple data points
   */
  public pushMany(items: T[]): void {
    items.forEach(item => this.push(item));
  }
  
  /**
   * Get all data points in chronological order
   */
  public getAll(): T[] {
    if (this.size === 0) {
      return [];
    }
    
    if (this.size < this.capacity) {
      // Buffer not full yet, return from start to head
      return this.buffer.slice(0, this.size);
    }
    
    // Buffer is full, return from head to end, then start to head
    return [
      ...this.buffer.slice(this.head),
      ...this.buffer.slice(0, this.head)
    ];
  }
  
  /**
   * Get the last N data points
   */
  public getLast(n: number): T[] {
    const all = this.getAll();
    return all.slice(-n);
  }
  
  /**
   * Get data points within a time range
   */
  public getRange(start: Date, end: Date): T[] {
    return this.getAll().filter(item => {
      const timestamp = new Date(item.timestamp);
      return timestamp >= start && timestamp <= end;
    });
  }
  
  /**
   * Clear the buffer
   */
  public clear(): void {
    this.head = 0;
    this.size = 0;
  }
  
  /**
   * Get current size
   */
  public getSize(): number {
    return this.size;
  }
  
  /**
   * Check if buffer is empty
   */
  public isEmpty(): boolean {
    return this.size === 0;
  }
  
  /**
   * Check if buffer is full
   */
  public isFull(): boolean {
    return this.size === this.capacity;
  }
}

