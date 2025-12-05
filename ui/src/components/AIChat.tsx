import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  MessageSquare, Send, Bot, User, Sparkles, 
  ChevronDown, Minimize2, Maximize2, X 
} from 'lucide-react';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  related_metrics?: any;
  suggested_actions?: string[];
}

const API_BASE = '';

export const AIChat = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: "Hello! I'm Ancient Report AI. I can analyze system performance, explain alerts, or predict resource usage. How can I help you today?",
      timestamp: new Date().toISOString()
    }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isOpen]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);

    try {
      const res = await fetch(`${API_BASE}/api/v3/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage.content })
      });

      if (res.ok) {
        const data = await res.json();
        const aiMessage: ChatMessage = {
          role: 'assistant',
          content: data.message,
          timestamp: new Date().toISOString(),
          related_metrics: data.related_metrics,
          suggested_actions: data.suggested_actions
        };
        setMessages(prev => [...prev, aiMessage]);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: "Sorry, I encountered an error processing your request. Please try again.",
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* Floating Action Button */}
      <AnimatePresence>
        {!isOpen && (
          <motion.button
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            onClick={() => setIsOpen(true)}
            className="fixed bottom-6 right-6 p-4 bg-neon-purple rounded-full shadow-lg shadow-neon-purple/30 hover:bg-neon-purple/80 transition-colors z-50 group"
          >
            <Sparkles className="w-6 h-6 text-white group-hover:animate-pulse" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* Chat Window */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ 
              opacity: 1, 
              y: 0, 
              scale: 1,
              height: isMinimized ? 'auto' : '600px',
              width: isMinimized ? '300px' : '400px'
            }}
            exit={{ opacity: 0, y: 50, scale: 0.9 }}
            className="fixed bottom-6 right-6 bg-[#0f111a] border border-white/10 rounded-2xl shadow-2xl z-50 overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="p-4 bg-white/5 border-b border-white/10 flex items-center justify-between cursor-pointer"
                 onClick={() => setIsMinimized(!isMinimized)}>
              <div className="flex items-center gap-3">
                <div className="p-2 bg-neon-purple/20 rounded-lg">
                  <Bot className="w-5 h-5 text-neon-purple" />
                </div>
                <div>
                  <h3 className="font-bold text-white text-sm">Ancient Report AI</h3>
                  <p className="text-xs text-green-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
                    Online
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button 
                  onClick={(e) => { e.stopPropagation(); setIsMinimized(!isMinimized); }}
                  className="p-1.5 hover:bg-white/10 rounded-lg text-gray-400 transition-colors"
                >
                  {isMinimized ? <Maximize2 className="w-4 h-4" /> : <Minimize2 className="w-4 h-4" />}
                </button>
                <button 
                  onClick={(e) => { e.stopPropagation(); setIsOpen(false); }}
                  className="p-1.5 hover:bg-red-500/20 hover:text-red-500 rounded-lg text-gray-400 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Messages Area */}
            {!isMinimized && (
              <>
                <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                  {messages.map((msg, idx) => (
                    <div 
                      key={idx} 
                      className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                    >
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                        msg.role === 'assistant' ? 'bg-neon-purple/20' : 'bg-blue-500/20'
                      }`}>
                        {msg.role === 'assistant' ? (
                          <Bot className="w-4 h-4 text-neon-purple" />
                        ) : (
                          <User className="w-4 h-4 text-blue-400" />
                        )}
                      </div>
                      
                      <div className={`max-w-[80%] space-y-2`}>
                        <div className={`p-3 rounded-2xl text-sm ${
                          msg.role === 'assistant' 
                            ? 'bg-white/5 text-gray-200 rounded-tl-none' 
                            : 'bg-blue-600 text-white rounded-tr-none'
                        }`}>
                          {msg.content}
                        </div>

                        {msg.related_metrics && (
                          <div className="bg-black/30 rounded-xl p-3 border border-white/5 text-xs">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-gray-400">Related Metric</span>
                              <Activity className="w-3 h-3 text-neon-blue" />
                            </div>
                            <div className="flex justify-between items-end">
                              <div>
                                <div className="text-gray-300">{msg.related_metrics.metric}</div>
                                <div className="text-gray-500">{msg.related_metrics.container}</div>
                              </div>
                              <div className="text-lg font-mono text-neon-blue">
                                {msg.related_metrics.value}%
                              </div>
                            </div>
                          </div>
                        )}

                        {msg.suggested_actions && msg.suggested_actions.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {msg.suggested_actions.map((action, i) => (
                              <button 
                                key={i}
                                onClick={() => setInput(action)}
                                className="px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-full text-xs text-neon-purple transition-colors"
                              >
                                {action}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  
                  {isTyping && (
                    <div className="flex gap-3">
                      <div className="w-8 h-8 rounded-full bg-neon-purple/20 flex items-center justify-center shrink-0">
                        <Bot className="w-4 h-4 text-neon-purple" />
                      </div>
                      <div className="bg-white/5 p-3 rounded-2xl rounded-tl-none flex gap-1 items-center">
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* Input Area */}
                <div className="p-4 bg-white/5 border-t border-white/10">
                  <div className="relative">
                    <input
                      type="text"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyPress={handleKeyPress}
                      placeholder="Ask about system status..."
                      className="w-full bg-black/20 border border-white/10 rounded-xl py-3 pl-4 pr-12 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-neon-purple/50 transition-colors"
                    />
                    <button
                      onClick={handleSend}
                      disabled={!input.trim() || isTyping}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-neon-purple/20 hover:bg-neon-purple/40 rounded-lg text-neon-purple transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Send className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};
