// web/api_gateway.js
// API Gateway Integration for PCZS

// Configuration
const API_ENDPOINT = 'https://REPLACE-WITH-YOUR-API-GATEWAY-URL.execute-api.us-east-2.amazonaws.com/prod';

// Function to save user preferences
async function savePreferences(preferences) {
    try {
        const response = await fetch(`${API_ENDPOINT}/preferences`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(preferences),
        });
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Preferences saved:', data);
        alert('Your comfort preferences have been saved!');
        return data;
    } catch (error) {
        console.error('Error saving preferences:', error);
        alert('Error saving preferences: ' + error.message);
    }
}

// Function to get user preferences
async function getPreferences(userId, workspaceId) {
    try {
        const response = await fetch(`${API_ENDPOINT}/preferences?user_id=${userId}&workspace_id=${workspaceId}`);
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Retrieved preferences:', data);
        return data;
    } catch (error) {
        console.error('Error getting preferences:', error);
        return null;
    }
}

// Function to get current telemetry data
async function getCurrentTelemetry(workspaceId) {
    try {
        const response = await fetch(`${API_ENDPOINT}/telemetry?workspace_id=${workspaceId}`);
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Retrieved telemetry:', data);
        
        // Update the dashboard with real data
        document.getElementById('current-temp').textContent = data.temperature;
        document.getElementById('current-humidity').textContent = data.humidity;
        document.getElementById('workspace-status').textContent = data.occupied ? 'Occupied' : 'Unoccupied';
        document.getElementById('fan-status').textContent = data.fan_state ? 'ON' : 'OFF';
        
        return data;
    } catch (error) {
        console.error('Error getting telemetry:', error);
        return null;
    }
}

// Initialize dashboard with user preferences
async function initializeDashboard() {
    const userId = 'user_1'; // In a real app, this would come from authentication
    const workspaceId = document.getElementById('workspace').value;
    
    // Get user preferences
    const preferences = await getPreferences(userId, workspaceId);
    if (preferences) {
        // Update form values with stored preferences
        document.getElementById('preferred-temp').value = preferences.preferred_temp;
        document.getElementById('temp-value').textContent = preferences.preferred_temp;
        
        document.getElementById('temp-threshold').value = preferences.temp_threshold;
        document.getElementById('threshold-value').textContent = preferences.temp_threshold;
        
        document.getElementById('preferred-humidity').value = preferences.preferred_humidity;
        document.getElementById('humidity-value').textContent = preferences.preferred_humidity;
        
        document.getElementById('humidity-threshold').value = preferences.humidity_threshold;
        document.getElementById('humidity-threshold-value').textContent = preferences.humidity_threshold;
    }
    
    // Start polling for telemetry updates
    setInterval(() => {
        getCurrentTelemetry(workspaceId);
    }, 10000); // Update every 10 seconds
}

// When the page loads
document.addEventListener('DOMContentLoaded', function() {
    // Comment out for testing without API
    // initializeDashboard();
});