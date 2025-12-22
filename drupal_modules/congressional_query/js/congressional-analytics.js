/**
 * @file
 * JavaScript for Congressional Query analytics page.
 */

(function ($, Drupal, drupalSettings) {
  "use strict";

  /**
   * Analytics behavior.
   */
  Drupal.behaviors.congressionalAnalytics = {
    attach: function (context, settings) {
      const $page = $(".congressional-analytics", context);

      if ($page.length === 0 || $page.hasClass("charts-initialized")) {
        return;
      }

      $page.addClass("charts-initialized");

      const data = drupalSettings.congressionalAnalytics || {};

      // Initialize charts.
      initHourlyChart(data.hourlyDistribution || {});
      initDailyChart(data.dailyDistribution || {});
      initResponseTimeChart(data.responseTimePercentiles || {});
      initMemberFiltersChart(data.topFilters || []);
      initModelsChart(data.queriesByModel || []);
      initTopWordsChart(data.topWords || {});

      /**
       * Initialize hourly distribution chart.
       */
      function initHourlyChart(hourlyData) {
        const canvas = document.getElementById("hourlyChart");
        if (!canvas) return;

        const labels = Object.keys(hourlyData).map(function (h) {
          return h + ":00";
        });
        const values = Object.values(hourlyData);

        new Chart(canvas, {
          type: "line",
          data: {
            labels: labels,
            datasets: [
              {
                label: Drupal.t("Queries"),
                data: values,
                borderColor: "rgb(75, 192, 192)",
                backgroundColor: "rgba(75, 192, 192, 0.2)",
                tension: 0.3,
                fill: true,
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
                  stepSize: 1,
                },
              },
            },
          },
        });
      }

      /**
       * Initialize daily distribution chart.
       */
      function initDailyChart(dailyData) {
        const canvas = document.getElementById("dailyChart");
        if (!canvas) return;

        const labels = Object.keys(dailyData);
        const values = Object.values(dailyData);

        new Chart(canvas, {
          type: "bar",
          data: {
            labels: labels,
            datasets: [
              {
                label: Drupal.t("Queries"),
                data: values,
                backgroundColor: "rgba(54, 162, 235, 0.7)",
                borderColor: "rgb(54, 162, 235)",
                borderWidth: 1,
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
                  stepSize: 1,
                },
              },
            },
          },
        });
      }

      /**
       * Initialize response time percentiles chart.
       */
      function initResponseTimeChart(percentiles) {
        const canvas = document.getElementById("responseTimeChart");
        if (!canvas) return;

        new Chart(canvas, {
          type: "bar",
          data: {
            labels: ["P50", "P90", "P99"],
            datasets: [
              {
                label: Drupal.t("Response Time (ms)"),
                data: [
                  percentiles.p50 || 0,
                  percentiles.p90 || 0,
                  percentiles.p99 || 0,
                ],
                backgroundColor: [
                  "rgba(75, 192, 192, 0.7)",
                  "rgba(255, 206, 86, 0.7)",
                  "rgba(255, 99, 132, 0.7)",
                ],
                borderColor: [
                  "rgb(75, 192, 192)",
                  "rgb(255, 206, 86)",
                  "rgb(255, 99, 132)",
                ],
                borderWidth: 1,
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
              },
            },
          },
        });
      }

      /**
       * Initialize member filters chart.
       */
      function initMemberFiltersChart(filtersData) {
        const canvas = document.getElementById("memberFiltersChart");
        if (!canvas || filtersData.length === 0) return;

        const labels = filtersData.map(function (f) {
          return f.filter || "All";
        });
        const values = filtersData.map(function (f) {
          return f.count;
        });

        new Chart(canvas, {
          type: "doughnut",
          data: {
            labels: labels,
            datasets: [
              {
                data: values,
                backgroundColor: [
                  "rgba(255, 99, 132, 0.7)",
                  "rgba(54, 162, 235, 0.7)",
                  "rgba(255, 206, 86, 0.7)",
                  "rgba(75, 192, 192, 0.7)",
                  "rgba(153, 102, 255, 0.7)",
                ],
                borderWidth: 1,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: "right",
              },
            },
          },
        });
      }

      /**
       * Initialize models chart.
       */
      function initModelsChart(modelsData) {
        const canvas = document.getElementById("modelsChart");
        if (!canvas || modelsData.length === 0) return;

        const labels = modelsData.map(function (m) {
          return m.model;
        });
        const values = modelsData.map(function (m) {
          return m.count;
        });

        new Chart(canvas, {
          type: "bar",
          data: {
            labels: labels,
            datasets: [
              {
                label: Drupal.t("Queries"),
                data: values,
                backgroundColor: "rgba(153, 102, 255, 0.7)",
                borderColor: "rgb(153, 102, 255)",
                borderWidth: 1,
              },
            ],
          },
          options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                display: false,
              },
            },
            scales: {
              x: {
                beginAtZero: true,
                ticks: {
                  stepSize: 1,
                },
              },
            },
          },
        });
      }

      /**
       * Initialize top words chart.
       */
      function initTopWordsChart(wordsData) {
        const canvas = document.getElementById("topWordsChart");
        if (!canvas || Object.keys(wordsData).length === 0) return;

        const labels = Object.keys(wordsData);
        const values = Object.values(wordsData);

        new Chart(canvas, {
          type: "bar",
          data: {
            labels: labels,
            datasets: [
              {
                label: Drupal.t("Frequency"),
                data: values,
                backgroundColor: "rgba(255, 159, 64, 0.7)",
                borderColor: "rgb(255, 159, 64)",
                borderWidth: 1,
              },
            ],
          },
          options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                display: false,
              },
            },
            scales: {
              x: {
                beginAtZero: true,
                ticks: {
                  stepSize: 1,
                },
              },
            },
          },
        });
      }
    },
  };
})(jQuery, Drupal, drupalSettings);
