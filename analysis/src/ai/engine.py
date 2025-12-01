import anthropic
import openai
import google.generativeai as genai
from typing import Dict, Any
import os
import logging

logger = logging.getLogger(__name__)


class AIEngine:
    """
    Unified AI engine supporting multiple LLM providers
    """
    
    def __init__(self, provider: str = "anthropic", model: str = None):
        self.provider = provider.lower()
        self.model = model
        
        if self.provider == "anthropic":
            self.client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
            self.model = model or "claude-3-5-sonnet-20241022"
            
        elif self.provider == "openai":
            openai.api_key = os.getenv("OPENAI_API_KEY")
            self.model = model or "gpt-4"
            
        elif self.provider == "google":
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            self.client = genai.GenerativeModel(model or "gemini-2.5-flash-lite")
            self.model = model or "gemini-2.5-flash-lite"
            
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")
        
        logger.info(f"AI Engine initialized: {self.provider} / {self.model}")
    
    async def generate_insights(self, prompt: str, temperature: float = 0.3) -> str:
        """
        Generate AI insights using the configured provider
        """
        try:
            if self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2000,
                    temperature=temperature,
                    messages=[{
                        "role": "user",
                        "content": prompt
                    }]
                )
                return response.content[0].text
                
            elif self.provider == "openai":
                response = openai.ChatCompletion.create(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": prompt
                    }],
                    temperature=temperature,
                    max_tokens=2000
                )
                return response.choices[0].message.content
                
            elif self.provider == "google":
                response = self.client.generate_content(
                    prompt,
                    generation_config={"temperature": temperature}
                )
                return response.text
                
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            raise
    
    def build_analysis_prompt(self, context: Dict[str, Any]) -> str:
        """
        Build a structured prompt for system analysis
        """
        prompt = f"""You are a senior SRE with 10+ years experience analyzing Linux server performance.

SYSTEM CONTEXT:
- Hostname: {context.get('hostname', 'unknown')}
- Uptime: {context.get('uptime', 'unknown')} days
- Hardware: {context.get('cpu_count', 'N/A')} cores, {context.get('memory_gb', 'N/A')}GB RAM
- OS: {context.get('os_info', 'Linux')}

CURRENT HOUR METRICS (vs 7-day baseline):
- CPU: {context.get('cpu_avg', 0):.1f}% avg, {context.get('cpu_peak', 0):.1f}% peak ({context.get('cpu_vs_baseline', 'N/A')})
- Memory: {context.get('memory_percent', 0):.1f}% used ({context.get('memory_vs_baseline', 'N/A')})
- Disk I/O: {context.get('disk_iops', 0)} IOPS, {context.get('disk_latency_ms', 0):.1f}ms latency ({context.get('disk_vs_baseline', 'N/A')})
- Network: {context.get('packets_total', 0)} packets, {context.get('packet_drops', 0)} drops ({context.get('network_vs_baseline', 'N/A')})

TOP PROCESSES:
- Top CPU Consumers: {context.get('top_cpu_processes', 'None')}
- Top Memory Consumers: {context.get('top_memory_processes', 'None')}
- Top Disk I/O Consumers: {context.get('top_disk_io_processes', 'None')}

ANOMALIES DETECTED:
{self._format_anomalies(context.get('anomalies', []))}

CONFIGURATION ISSUES FOUND:
{self._format_config_issues(context.get('config_issues', []))}

PROVIDE:
1. Critical Alerts (if any urgent issues requiring immediate attention)
2. 3-5 Actionable Recommendations (specific, technical, implementable)
3. Capacity Forecast Assessment (weeks until resource exhaustion)
4. Configuration Optimizations (specific parameters with values and impact)

Format as JSON with these keys:
{{
  "critical_alerts": [...],
  "recommendations": [...],
  "capacity_forecast": {{...}},
  "config_optimizations": [...]
}}

Be concise, technical, and focus on actionable insights.
Use specific numbers and timeframes. Explain the "why" behind each recommendation.
"""
        return prompt
    
    def _format_anomalies(self, anomalies: list) -> str:
        if not anomalies:
            return "None detected"
        
        lines = []
        for anomaly in anomalies[:5]:  # Top 5 anomalies
            lines.append(f"- {anomaly.get('metric', 'unknown')}: {anomaly.get('description', 'N/A')}")
        return "\n".join(lines)
    
    def _format_config_issues(self, issues: list) -> str:
        if not issues:
            return "None detected"
        
        lines = []
        for issue in issues[:5]:  # Top 5 issues
            lines.append(f"- {issue.get('parameter', 'unknown')}: {issue.get('reason', 'N/A')}")
        return "\n".join(lines)
