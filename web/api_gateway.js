// api_gateway.js
// API Gateway Integration for PCZS

// Configuration
const API_ENDPOINT = 'https://kyqa443czf.execute-api.us-east-2.amazonaws.com/prod';

// Function to save user preferences
async function savePreferences(preferences) {
    try {
        console.log('Saving preferences:', preferences);
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
        
        // Update form with retrieved preferences
        if (data) {
            document.getElementById('preferred-temp').value = data.preferred_temp;
            document.getElementById('temp-val').textContent = data.preferred_temp;
            
            document.getElementById('temp-threshold').value = data.temp_threshold;
            document.getElementById('temp-thresh-val').textContent = data.temp_threshold;
            
            document.getElementById('preferred-humidity').value = data.preferred_humidity;
            document.getElementById('humidity-val').textContent = data.preferred_humidity;
            
            document.getElementById('humidity-threshold').value = data.humidity_threshold;
            document.getElementById('humidity-thresh-val').textContent = data.humidity_threshold;
        }
        
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
        return data;
    } catch (error) {
        console.error('Error getting telemetry:', error);
        return null;
    }
}

// Initialize dashboard with preferences when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Get user preferences when page loads
    const userId = 'user_1'; // In a real app, this would come from authentication
    const workspaceId = document.getElementById('workspace-id').value;
    getPreferences(userId, workspaceId);
});

// Make functions available globally
window.savePreferences = savePreferences;
window.getPreferences = getPreferences;
window.getCurrentTelemetry = getCurrentTelemetry;