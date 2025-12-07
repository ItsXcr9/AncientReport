import { useState, useEffect } from 'react';

// Feature toggle configuration types
export interface UIConfig {
  features: {
    containerTopology: {
      enabled: boolean;
    };
    metricsHistory: {
      showForAllServers: boolean;
    };
  };
}

// Default configuration (used as fallback)
const defaultConfig: UIConfig = {
  features: {
    containerTopology: {
      enabled: false,
    },
    metricsHistory: {
      showForAllServers: false,
    },
  },
};

// Simple YAML parser for basic config structure
function parseSimpleYaml(yamlText: string): UIConfig {
  const config = { ...defaultConfig };
  const lines = yamlText.split('\n');
  
  let currentSection = '';
  let currentFeature = '';
  
  for (const line of lines) {
    const trimmed = line.trim();
    
    // Skip comments and empty lines
    if (!trimmed || trimmed.startsWith('#')) continue;
    
    // Check for section headers
    if (trimmed === 'features:') {
      currentSection = 'features';
      continue;
    }
    
    // Check for feature names
    if (currentSection === 'features') {
      if (trimmed === 'containerTopology:') {
        currentFeature = 'containerTopology';
        continue;
      }
      if (trimmed === 'metricsHistory:') {
        currentFeature = 'metricsHistory';
        continue;
      }
      
      // Parse boolean values
      const match = trimmed.match(/^(\w+):\s*(true|false)/);
      if (match) {
        const [, key, value] = match;
        const boolValue = value === 'true';
        
        if (currentFeature === 'containerTopology' && key === 'enabled') {
          config.features.containerTopology.enabled = boolValue;
        }
        if (currentFeature === 'metricsHistory' && key === 'showForAllServers') {
          config.features.metricsHistory.showForAllServers = boolValue;
        }
      }
    }
  }
  
  return config;
}

// Hook to load and provide UI configuration
export function useConfig(): UIConfig {
  const [config, setConfig] = useState<UIConfig>(defaultConfig);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const response = await fetch('/config.yaml');
        if (response.ok) {
          const yamlText = await response.text();
          const parsedConfig = parseSimpleYaml(yamlText);
          setConfig(parsedConfig);
        }
      } catch (error) {
        console.warn('Failed to load config.yaml, using defaults:', error);
      }
    };

    loadConfig();
  }, []);

  return config;
}
