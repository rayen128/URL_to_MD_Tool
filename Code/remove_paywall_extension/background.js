chrome.action.onClicked.addListener(function(tab) {
  chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
    var currentUrl = decodeURIComponent(tabs[0].url);
    var modifiedUrl = 'https://removepaywalls.com/' + currentUrl;
    chrome.tabs.update({url: modifiedUrl});
  });
});
