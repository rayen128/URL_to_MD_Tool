document.addEventListener('DOMContentLoaded', function() {
  var removePaywallsButton = document.getElementById('removePaywallsButton');
  removePaywallsButton.addEventListener('click', function() {
    chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
      var currentUrl = decodeURIComponent(tabs[0].url);
      var modifiedUrl = 'https://removepaywalls.com/' + currentUrl;
      chrome.tabs.update({url: modifiedUrl});
    });
  });
});
