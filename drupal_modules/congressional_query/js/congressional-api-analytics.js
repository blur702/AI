/**
 * @file
 * JavaScript for Congressional API Analytics page.
 */

(function ($, Drupal, drupalSettings, once) {
  "use strict";

  Drupal.behaviors.congressionalApiAnalytics = {
    attach: function (context, settings) {
      const elements = once(
        "api-analytics",
        ".congressional-api-analytics",
        context,
      );

      if (elements.length === 0) {
        return;
      }

      const analyticsData = settings.congressionalApiAnalytics || {};

      // Initialize hourly chart.
      this.initHourlyChart(analyticsData.hourlyDistribution || {});

      // Initialize endpoint chart.
      this.initEndpointChart(analyticsData.requestsByEndpoint || {});
    },

    initHourlyChart: function (data) {
      const canvas = document.getElementById("hourly-chart");
      if (!canvas || typeof Chart === "undefined") {
        return;
      }

      const labels = [];
      const values = [];

      // Convert object to arrays.
      for (let i = 1; i <= 24; i++) {
        labels.push(`${i}h ago`);
        values.push(data[i] || 0);
      }

      // Reverse to show oldest first.
      labels.reverse();
      values.reverse();

      new Chart(canvas, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Requests",
              data: values,
              borderColor: "#0073e6",
              backgroundColor: "rgba(0, 115, 230, 0.1)",
              fill: true,
              tension: 0.3,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false,
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: {
                precision: 0,
              },
            },
          },
        },
      });
    },

    initEndpointChart: function (data) {
      const canvas = document.getElementById("endpoint-chart");
      if (!canvas || typeof Chart === "undefined") {
        return;
      }

      const labels = Object.keys(data);
      const values = Object.values(data).map((v) => parseInt(v, 10));

      if (labels.length === 0) {
        return;
      }

      // Truncate long endpoint names.
      const shortLabels = labels.map((label) => {
        if (label.length > 30) {
          return "..." + label.slice(-27);
        }
        return label;
      });

      new Chart(canvas, {
        type: "bar",
        data: {
          labels: shortLabels,
          datasets: [
            {
              label: "Requests",
              data: values,
              backgroundColor: [
                "#0073e6",
                "#00a65a",
                "#f39c12",
                "#dd4b39",
                "#605ca8",
              ],
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false,
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: {
                precision: 0,
              },
            },
          },
        },
      });
    },
  };
})(jQuery, Drupal, drupalSettings, once);
