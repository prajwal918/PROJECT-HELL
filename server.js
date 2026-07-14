const express = require('express');

const app = express();
const port = process.env.PORT || 80;

app.get('/', (req, res) => {
    try {
        res.json({ status: 'success', message: 'Welcome to PROJECT-HELL' });
    } catch (error) {
        console.error('Error processing request:', error);
        res.status(500).json({ status: 'error', message: 'Internal Server Error' });
    }
});

const startServer = () => {
    try {
        app.listen(port, () => {
            console.log(`Server is running on port ${port}`);
        });
    } catch (error) {
        console.error('Failed to start server:', error);
        process.exit(1);
    }
};

startServer();
